"""
Cloud Pattern Identifier — ISS / Webcam Edition
================================================
Captura vídeo em tempo real (webcam ou arquivo .mp4) e identifica
padrões de nuvens usando OpenCV com técnicas de visão computacional.

Tipos detectados:
  - Cumulonimbus  → nuvens escuras, alta cobertura, tempestade
  - Cumulus       → nuvens com bordas definidas, brancas isoladas
  - Stratus       → camada uniforme de baixa altitude
  - Cirrus        → finas, alta altitude, pouco contraste
  - Clear Sky     → céu limpo / ausência de nuvens

Pipeline:
  1. Captura de frame
  2. Segmentação por HSV + thresholding adaptativo
  3. Análise de textura (variância, gradiente Sobel)
  4. Análise morfológica (contornos, área, compacidade)
  5. Classificação por regras heurísticas
  6. Renderização de bounding boxes + labels na tela
"""

import cv2
import numpy as np
import time
import sys
import os
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────
# Configurações
# ──────────────────────────────────────────────

WINDOW_NAME = "Cloud Pattern Identifier — ISS"

# Limiares de classificação (tunáveis)
COVERAGE_DARK_THRESH   = 0.30   # fração do frame com pixels escuros → cumulonimbus
COVERAGE_CLOUD_MIN     = 0.05   # cobertura mínima para considerar presença de nuvem
COVERAGE_CLEAR_MAX     = 0.08   # cobertura abaixo disso → clear sky
TEXTURE_HIGH           = 18.0   # desvio-padrão alto → textura rugosa (cumulonimbus/cumulus)
TEXTURE_LOW            = 6.0    # desvio-padrão baixo → textura suave (stratus/cirrus)
EDGE_DENSITY_HIGH      = 0.06   # densidade de bordas alta → cumulus bem definido
EDGE_DENSITY_CIRRUS    = 0.015  # densidade de bordas muito baixa → cirrus


# Cores BGR por classe
CLASS_COLORS = {
    "Cumulonimbus": (60,  60,  200),   # vermelho escuro
    "Cumulus":      (50,  200,  50),   # verde
    "Stratus":      (200, 150,  50),   # azul
    "Cirrus":       (200, 200, 200),   # cinza claro
    "Clear Sky":    (180, 220,  80),   # verde-azulado
    "Analisando…":  (120, 120, 120),
}

CLASS_DESCRIPTIONS = {
    "Cumulonimbus": "Tempestade / alta cobertura escura",
    "Cumulus":      "Nuvens isoladas com bordas definidas",
    "Stratus":      "Camada uniforme — baixa textura",
    "Cirrus":       "Alta altitude — finas e esparsas",
    "Clear Sky":    "Cobertura de nuvens mínima",
    "Analisando…":  "",
}


# ──────────────────────────────────────────────
# Estruturas de dados
# ──────────────────────────────────────────────

@dataclass
class CloudRegion:
    label: str
    confidence: float           # 0.0 – 1.0
    bbox: tuple                 # (x, y, w, h)
    area_fraction: float        # fração da área do frame


@dataclass
class FrameAnalysis:
    cloud_class: str
    confidence: float
    regions: list = field(default_factory=list)
    coverage: float = 0.0
    texture_score: float = 0.0
    edge_density: float = 0.0
    fps: float = 0.0


# ──────────────────────────────────────────────
# Pipeline de análise
# ──────────────────────────────────────────────

def extract_cloud_mask(frame: np.ndarray) -> np.ndarray:
    """
    Segmenta regiões de nuvem via HSV + threshold adaptativo.
    Nuvens tendem a ser brilhantes (alta Value) e pouco saturadas.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    _, s, v = cv2.split(hsv)

    # Nuvens = pouca saturação + brilho médio/alto
    cloud_mask = cv2.inRange(hsv, (0, 0, 100), (180, 60, 255))

    # Threshold adaptativo em escala de cinza (captura stratus difusos)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    adaptive = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=51, C=-5
    )

    combined = cv2.bitwise_or(cloud_mask, adaptive)

    # Morfologia para limpar ruído
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN,  kernel)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
    return combined


def compute_texture(gray: np.ndarray) -> float:
    """Desvio padrão local via Laplaciano — mede rugosidade da textura."""
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(np.std(lap))


def compute_edge_density(gray: np.ndarray) -> float:
    """Densidade de bordas Sobel normalizada pela área do frame."""
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(sobelx**2 + sobely**2)
    edge_pixels = np.sum(mag > 30)
    return edge_pixels / (gray.shape[0] * gray.shape[1])


def find_cloud_regions(mask: np.ndarray, frame_area: int) -> list:
    """Detecta contornos e filtra regiões significativas."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    min_area = frame_area * 0.005   # ignora regiões < 0.5% do frame

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        regions.append((x, y, w, h, area / frame_area))

    # Ordena por área decrescente, limita a 8 regiões
    regions.sort(key=lambda r: r[4], reverse=True)
    return regions[:8]


def classify_frame(coverage: float, texture: float, edge_density: float,
                   dark_fraction: float) -> tuple:
    """
    Classificação por regras heurísticas baseadas em:
      - coverage       : fração do frame com nuvens
      - texture        : rugosidade (desvio Laplaciano)
      - edge_density   : densidade de bordas Sobel
      - dark_fraction  : fração de pixels escuros (tempestade)
    Retorna (classe, confiança).
    """
    if coverage < COVERAGE_CLEAR_MAX:
        conf = 1.0 - (coverage / COVERAGE_CLEAR_MAX)
        return "Clear Sky", round(conf * 0.95 + 0.05, 2)

    if dark_fraction > COVERAGE_DARK_THRESH and texture > TEXTURE_HIGH:
        conf = min(1.0, dark_fraction * 2.5)
        return "Cumulonimbus", round(conf, 2)

    if edge_density > EDGE_DENSITY_HIGH and texture > TEXTURE_HIGH:
        conf = min(1.0, edge_density / (EDGE_DENSITY_HIGH * 1.5))
        return "Cumulus", round(conf, 2)

    if texture < TEXTURE_LOW and coverage > 0.25:
        conf = min(1.0, coverage * 1.5)
        return "Stratus", round(conf, 2)

    if edge_density < EDGE_DENSITY_CIRRUS and coverage < 0.35:
        conf = 1.0 - (edge_density / EDGE_DENSITY_CIRRUS)
        return "Cirrus", round(max(conf, 0.4), 2)

    # Fallback: cumulus moderado
    conf = min(0.65, coverage)
    return "Cumulus", round(conf, 2)


def analyze_frame(frame: np.ndarray, fps: float = 0.0) -> FrameAnalysis:
    """Executa o pipeline completo de análise em um frame."""
    h, w = frame.shape[:2]
    frame_area = h * w

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = extract_cloud_mask(frame)

    coverage     = float(np.sum(mask > 0)) / frame_area
    texture      = compute_texture(gray)
    edge_density = compute_edge_density(gray)

    # Fração de pixels escuros (nuvens de tempestade)
    dark_mask    = cv2.inRange(frame, (0, 0, 0), (80, 80, 80))
    dark_fraction = float(np.sum(dark_mask > 0)) / frame_area

    cloud_class, confidence = classify_frame(coverage, texture, edge_density, dark_fraction)

    raw_regions = find_cloud_regions(mask, frame_area)
    regions = [
        CloudRegion(
            label=cloud_class,
            confidence=round(confidence * (0.7 + 0.3 * af), 2),
            bbox=(x, y, ww, hh),
            area_fraction=af
        )
        for (x, y, ww, hh, af) in raw_regions
    ]

    return FrameAnalysis(
        cloud_class=cloud_class,
        confidence=confidence,
        regions=regions,
        coverage=round(coverage, 3),
        texture_score=round(texture, 2),
        edge_density=round(edge_density, 4),
        fps=fps,
    )


# ──────────────────────────────────────────────
# Renderização / HUD
# ──────────────────────────────────────────────

def draw_bounding_boxes(frame: np.ndarray, analysis: FrameAnalysis) -> np.ndarray:
    """Desenha bounding boxes e labels nas regiões detectadas."""
    color = CLASS_COLORS.get(analysis.cloud_class, (200, 200, 200))

    for region in analysis.regions:
        x, y, w, h = region.bbox
        # Box principal
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

        # Label compacto dentro/acima da box
        label_txt = f"{region.label} {region.confidence:.0%}"
        font      = cv2.FONT_HERSHEY_SIMPLEX
        scale     = 0.45
        thickness = 1
        (tw, th), _ = cv2.getTextSize(label_txt, font, scale, thickness)

        ty = y - 6 if y > th + 6 else y + th + 6
        cv2.rectangle(frame, (x, ty - th - 4), (x + tw + 6, ty + 2), color, -1)
        cv2.putText(frame, label_txt, (x + 3, ty - 1),
                    font, scale, (255, 255, 255), thickness, cv2.LINE_AA)

    return frame


def draw_hud(frame: np.ndarray, analysis: FrameAnalysis) -> np.ndarray:
    """Painel de informações no canto superior esquerdo."""
    color = CLASS_COLORS.get(analysis.cloud_class, (200, 200, 200))
    h_frame = frame.shape[0]

    # Fundo semi-transparente
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (320, 175), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    font   = cv2.FONT_HERSHEY_SIMPLEX
    y0     = 38

    # Título
    cv2.putText(frame, "CLOUD IDENTIFIER", (20, y0),
                font, 0.55, (200, 200, 200), 1, cv2.LINE_AA)

    # Classe principal
    cv2.putText(frame, analysis.cloud_class, (20, y0 + 30),
                font, 0.85, color, 2, cv2.LINE_AA)

    # Barra de confiança
    bar_x, bar_y, bar_w, bar_h = 20, y0 + 42, 200, 10
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (60, 60, 60), -1)
    cv2.rectangle(frame, (bar_x, bar_y),
                  (bar_x + int(bar_w * analysis.confidence), bar_y + bar_h), color, -1)
    cv2.putText(frame, f"{analysis.confidence:.0%}", (bar_x + bar_w + 8, bar_y + 9),
                font, 0.4, (200, 200, 200), 1, cv2.LINE_AA)

    # Métricas
    metrics = [
        f"Cobertura : {analysis.coverage:.1%}",
        f"Textura   : {analysis.texture_score:.1f}",
        f"Bordas    : {analysis.edge_density:.4f}",
        f"FPS       : {analysis.fps:.1f}",
    ]
    for i, m in enumerate(metrics):
        cv2.putText(frame, m, (20, y0 + 70 + i * 18),
                    font, 0.38, (180, 180, 180), 1, cv2.LINE_AA)

    # Descrição
    desc = CLASS_DESCRIPTIONS.get(analysis.cloud_class, "")
    cv2.putText(frame, desc, (20, y0 + 70 + len(metrics) * 18 + 4),
                font, 0.35, (140, 140, 140), 1, cv2.LINE_AA)

    # Legenda de teclas (canto inferior)
    hint = "[Q] Sair  [S] Salvar frame  [M] Mascara"
    cv2.putText(frame, hint, (10, h_frame - 12),
                font, 0.38, (120, 120, 120), 1, cv2.LINE_AA)

    return frame


# ──────────────────────────────────────────────
# Loop principal
# ──────────────────────────────────────────────

def run(source: str = "0") -> None:
    """
    Inicia o pipeline de captura e análise.

    Args:
        source: "0" para webcam, caminho para .mp4 para arquivo de vídeo.
    """
    # Converte "0" → int para webcam
    cap_source: int | str = int(source) if source.isdigit() else source

    cap = cv2.VideoCapture(cap_source)
    if not cap.isOpened():
        print(f"[ERRO] Não foi possível abrir a fonte de vídeo: {source}")
        sys.exit(1)

    print(f"[INFO] Fonte: {source}")
    print("[INFO] Pressione Q para sair, S para salvar frame, M para alternar máscara")

    show_mask   = False
    frame_count = 0
    t_prev      = time.perf_counter()
    fps         = 0.0

    os.makedirs("output", exist_ok=True)

    while True:
        ret, frame = cap.read()
        if not ret:
            # Arquivo terminou → reinicia
            if isinstance(cap_source, str):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            break

        frame_count += 1

        # Calcula FPS com média móvel
        t_now = time.perf_counter()
        fps   = 0.9 * fps + 0.1 * (1.0 / max(t_now - t_prev, 1e-6))
        t_prev = t_now

        # Análise a cada frame (pode ser feito a cada N frames para performance)
        analysis = analyze_frame(frame, fps)

        if show_mask:
            mask = extract_cloud_mask(frame)
            display = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        else:
            display = frame.copy()
            display = draw_bounding_boxes(display, analysis)

        display = draw_hud(display, analysis)

        cv2.imshow(WINDOW_NAME, display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break
        elif key == ord('s'):
            fname = f"output/frame_{frame_count:05d}_{analysis.cloud_class.replace(' ', '_')}.jpg"
            cv2.imwrite(fname, display)
            print(f"[INFO] Frame salvo: {fname}")
        elif key == ord('m'):
            show_mask = not show_mask

    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] Encerrado.")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "0"
    run(source)