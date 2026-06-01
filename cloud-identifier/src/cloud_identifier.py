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
  7. Envio das leituras para a API (opcional, --api)
"""

import cv2
import numpy as np
import time
import sys
import os
import json
import threading
import queue
from dataclasses import dataclass, field
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode


# ──────────────────────────────────────────────
# Configurações
# ──────────────────────────────────────────────

WINDOW_NAME = "Cloud Pattern Identifier — ISS"

# Limiares de classificação (tunáveis)
COVERAGE_DARK_THRESH   = 0.30
COVERAGE_CLOUD_MIN     = 0.05
COVERAGE_CLEAR_MAX     = 0.08
TEXTURE_HIGH           = 18.0
TEXTURE_LOW            = 6.0
EDGE_DENSITY_HIGH      = 0.06
EDGE_DENSITY_CIRRUS    = 0.015

# Cores BGR por classe
CLASS_COLORS = {
    "Cumulonimbus": (60,  60,  200),
    "Cumulus":      (50,  200,  50),
    "Stratus":      (200, 150,  50),
    "Cirrus":       (200, 200, 200),
    "Clear Sky":    (180, 220,  80),
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
    confidence: float
    bbox: tuple
    area_fraction: float


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
# API Client (envia leituras em background)
# ──────────────────────────────────────────────

class ApiClient:
    """
    Cliente HTTP leve (sem dependências externas).
    Envia leituras para a API em uma thread separada
    para não bloquear o loop de vídeo.
    """

    def __init__(self, base_url: str, username: str, password: str,
                 sensor_id: str, send_every: int = 30) -> None:
        self.base_url   = base_url.rstrip("/")
        self.sensor_id  = sensor_id
        self.send_every = send_every   # envia a cada N frames
        self._token: Optional[str] = None
        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._connected = False
        self._status_msg = "API: conectando..."
        self._username = username
        self._password = password

        # Thread de envio em background
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

        # Login inicial em thread separada para não travar startup
        threading.Thread(target=self._login, daemon=True).start()

    def _request(self, method: str, path: str,
                 body: Optional[dict] = None,
                 auth: bool = True) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"}
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            if e.code == 401:
                self._token = None
                self._connected = False
                self._status_msg = "API: token expirado"
            return None
        except URLError:
            self._connected = False
            self._status_msg = "API: sem conexão"
            return None

    def _login(self) -> None:
        result = self._request("POST", "/auth/login", {
            "username": self._username,
            "password": self._password,
        }, auth=False)
        if result and "access_token" in result:
            self._token = result["access_token"]
            self._connected = True
            self._status_msg = f"API: ✓ sensor {self.sensor_id[:8]}…"
            print(f"[API] Conectado — sensor: {self.sensor_id[:8]}…")
        else:
            self._status_msg = "API: falha no login"
            print("[API] Falha no login — verifique usuário/senha e se a API está rodando")

    def _worker(self) -> None:
        """Loop em background que consome a fila e envia para a API."""
        while True:
            try:
                payload = self._queue.get(timeout=1)
                if not self._token:
                    self._login()
                if self._token:
                    self._request("POST", "/readings/", payload)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[API] Erro no worker: {e}")

    def send(self, analysis: FrameAnalysis) -> None:
        """Enfileira uma leitura para envio (não bloqueia)."""
        if not self._connected:
            return
        payload = {
            "sensor_id":     self.sensor_id,
            "cloud_class":   analysis.cloud_class,
            "confidence":    analysis.confidence,
            "coverage":      analysis.coverage,
            "texture_score": analysis.texture_score,
            "edge_density":  analysis.edge_density,
        }
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            pass   # descarta se fila cheia (não bloqueia o vídeo)

    @property
    def status(self) -> str:
        return self._status_msg

    @property
    def connected(self) -> bool:
        return self._connected


def get_or_create_sensor(base_url: str, token: str,
                          sensor_name: str = "ISS-CAM-LOCAL") -> Optional[str]:
    """
    Busca o primeiro sensor disponível na API.
    Se não existir nenhum, cria um novo automaticamente.
    Retorna o sensor_id.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    # Lista sensores existentes
    req = Request(f"{base_url}/sensors/", headers=headers)
    try:
        with urlopen(req, timeout=5) as resp:
            sensors = json.loads(resp.read())
            if sensors:
                sid = sensors[0]["id"]
                print(f"[API] Usando sensor existente: {sensors[0]['name']} ({sid[:8]}…)")
                return sid
    except Exception:
        pass

    # Cria sensor novo
    body = json.dumps({
        "name": sensor_name,
        "sensor_type": "cloud_vision",
        "latitude": 51.6,
        "longitude": 0.0,
        "altitude_km": 408.0,
        "video_source": "0",
    }).encode()
    req = Request(f"{base_url}/sensors/", data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=5) as resp:
            sensor = json.loads(resp.read())
            print(f"[API] Sensor criado: {sensor['name']} ({sensor['id'][:8]}…)")
            return sensor["id"]
    except Exception as e:
        print(f"[API] Não foi possível criar sensor: {e}")
        return None


# ──────────────────────────────────────────────
# Pipeline de análise
# ──────────────────────────────────────────────

def extract_cloud_mask(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    cloud_mask = cv2.inRange(hsv, (0, 0, 100), (180, 60, 255))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    adaptive = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=51, C=-5
    )
    combined = cv2.bitwise_or(cloud_mask, adaptive)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN,  kernel)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
    return combined


def compute_texture(gray: np.ndarray) -> float:
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(np.std(lap))


def compute_edge_density(gray: np.ndarray) -> float:
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(sobelx**2 + sobely**2)
    edge_pixels = np.sum(mag > 30)
    return edge_pixels / (gray.shape[0] * gray.shape[1])


def find_cloud_regions(mask: np.ndarray, frame_area: int) -> list:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    min_area = frame_area * 0.005
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        regions.append((x, y, w, h, area / frame_area))
    regions.sort(key=lambda r: r[4], reverse=True)
    return regions[:8]


def classify_frame(coverage: float, texture: float,
                   edge_density: float, dark_fraction: float) -> tuple:
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
    conf = min(0.65, coverage)
    return "Cumulus", round(conf, 2)


def analyze_frame(frame: np.ndarray, fps: float = 0.0) -> FrameAnalysis:
    h, w = frame.shape[:2]
    frame_area = h * w
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = extract_cloud_mask(frame)
    coverage     = float(np.sum(mask > 0)) / frame_area
    texture      = compute_texture(gray)
    edge_density = compute_edge_density(gray)
    dark_mask    = cv2.inRange(frame, (0, 0, 0), (80, 80, 80))
    dark_fraction = float(np.sum(dark_mask > 0)) / frame_area
    cloud_class, confidence = classify_frame(coverage, texture, edge_density, dark_fraction)
    raw_regions = find_cloud_regions(mask, frame_area)
    regions = [
        CloudRegion(
            label=cloud_class,
            confidence=round(confidence * (0.7 + 0.3 * af), 2),
            bbox=(x, y, ww, hh),
            area_fraction=af,
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
    color = CLASS_COLORS.get(analysis.cloud_class, (200, 200, 200))
    for region in analysis.regions:
        x, y, w, h = region.bbox
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        label_txt = f"{region.label} {region.confidence:.0%}"
        font  = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.45
        (tw, th), _ = cv2.getTextSize(label_txt, font, scale, 1)
        ty = y - 6 if y > th + 6 else y + th + 6
        cv2.rectangle(frame, (x, ty - th - 4), (x + tw + 6, ty + 2), color, -1)
        cv2.putText(frame, label_txt, (x + 3, ty - 1),
                    font, scale, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


def draw_hud(frame: np.ndarray, analysis: FrameAnalysis,
             api_status: str = "") -> np.ndarray:
    color    = CLASS_COLORS.get(analysis.cloud_class, (200, 200, 200))
    h_frame  = frame.shape[0]
    overlay  = frame.copy()
    hud_h    = 195 if api_status else 175
    cv2.rectangle(overlay, (10, 10), (320, hud_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    font = cv2.FONT_HERSHEY_SIMPLEX
    y0   = 38
    cv2.putText(frame, "CLOUD IDENTIFIER", (20, y0),
                font, 0.55, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, analysis.cloud_class, (20, y0 + 30),
                font, 0.85, color, 2, cv2.LINE_AA)

    bar_x, bar_y, bar_w, bar_h = 20, y0 + 42, 200, 10
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (60, 60, 60), -1)
    cv2.rectangle(frame, (bar_x, bar_y),
                  (bar_x + int(bar_w * analysis.confidence), bar_y + bar_h), color, -1)
    cv2.putText(frame, f"{analysis.confidence:.0%}", (bar_x + bar_w + 8, bar_y + 9),
                font, 0.4, (200, 200, 200), 1, cv2.LINE_AA)

    metrics = [
        f"Cobertura : {analysis.coverage:.1%}",
        f"Textura   : {analysis.texture_score:.1f}",
        f"Bordas    : {analysis.edge_density:.4f}",
        f"FPS       : {analysis.fps:.1f}",
    ]
    for i, m in enumerate(metrics):
        cv2.putText(frame, m, (20, y0 + 70 + i * 18),
                    font, 0.38, (180, 180, 180), 1, cv2.LINE_AA)

    desc = CLASS_DESCRIPTIONS.get(analysis.cloud_class, "")
    cv2.putText(frame, desc, (20, y0 + 70 + len(metrics) * 18 + 4),
                font, 0.35, (140, 140, 140), 1, cv2.LINE_AA)

    # Status da API
    if api_status:
        api_color = (80, 200, 80) if "✓" in api_status else (120, 120, 200)
        cv2.putText(frame, api_status, (20, hud_h - 12),
                    font, 0.35, api_color, 1, cv2.LINE_AA)

    hint = "[Q] Sair  [S] Salvar frame  [M] Mascara"
    cv2.putText(frame, hint, (10, h_frame - 12),
                font, 0.38, (120, 120, 120), 1, cv2.LINE_AA)

    return frame


# ──────────────────────────────────────────────
# Loop principal
# ──────────────────────────────────────────────

def run(source: str = "0",
        api_url: Optional[str] = None,
        api_user: str = "admin",
        api_pass: str = "admin123",
        send_every: int = 30) -> None:
    """
    Inicia o pipeline de captura e análise.

    Args:
        source:     "0" para webcam, caminho para .mp4 para vídeo.
        api_url:    URL da API (ex: http://localhost:8000). Se None, desativa integração.
        api_user:   Usuário para login na API.
        api_pass:   Senha para login na API.
        send_every: Envia leitura a cada N frames (padrão: 30 ≈ 1 leitura/s a 30fps).
    """
    cap_source: int | str = int(source) if source.isdigit() else source

    cap = cv2.VideoCapture(cap_source)
    if not cap.isOpened():
        print(f"[ERRO] Não foi possível abrir a fonte de vídeo: {source}")
        sys.exit(1)

    print(f"[INFO] Fonte: {source}")
    print("[INFO] Pressione Q para sair, S para salvar frame, M para alternar máscara")

    # ── Inicializa cliente de API (opcional) ──
    api_client: Optional[ApiClient] = None
    if api_url:
        print(f"[API] Conectando a {api_url}…")
        # Faz login síncrono para pegar o sensor_id antes de iniciar o loop
        login_body = json.dumps({"username": api_user, "password": api_pass}).encode()
        login_req  = Request(f"{api_url}/auth/login",
                             data=login_body,
                             headers={"Content-Type": "application/json"},
                             method="POST")
        token = None
        try:
            with urlopen(login_req, timeout=5) as resp:
                token = json.loads(resp.read()).get("access_token")
        except Exception as e:
            print(f"[API] Falha no login: {e} — continuando sem API")

        if token:
            sensor_id = get_or_create_sensor(api_url, token)
            if sensor_id:
                api_client = ApiClient(
                    base_url=api_url,
                    username=api_user,
                    password=api_pass,
                    sensor_id=sensor_id,
                    send_every=send_every,
                )
                # Injeta token já obtido para evitar segundo login
                api_client._token     = token
                api_client._connected = True
                api_client._status_msg = f"API: ✓ sensor {sensor_id[:8]}…"

    show_mask   = False
    frame_count = 0
    t_prev      = time.perf_counter()
    fps         = 0.0

    os.makedirs("output", exist_ok=True)

    while True:
        ret, frame = cap.read()
        if not ret:
            if isinstance(cap_source, str):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            break

        frame_count += 1

        t_now = time.perf_counter()
        fps   = 0.9 * fps + 0.1 * (1.0 / max(t_now - t_prev, 1e-6))
        t_prev = t_now

        analysis = analyze_frame(frame, fps)

        # ── Envia para API a cada N frames ──
        if api_client and frame_count % send_every == 0:
            api_client.send(analysis)

        if show_mask:
            mask    = extract_cloud_mask(frame)
            display = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        else:
            display = frame.copy()
            display = draw_bounding_boxes(display, analysis)

        api_status = api_client.status if api_client else ""
        display = draw_hud(display, analysis, api_status=api_status)

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
    import argparse

    parser = argparse.ArgumentParser(description="Cloud Pattern Identifier")
    parser.add_argument("source",       nargs="?", default="0",
                        help="Fonte de vídeo: 0 para webcam, ou caminho para .mp4")
    parser.add_argument("--api",        default=None,
                        help="URL da API (ex: http://localhost:8000). Ativa envio em tempo real.")
    parser.add_argument("--user",       default="admin",   help="Usuário da API")
    parser.add_argument("--password",   default="admin123", help="Senha da API")
    parser.add_argument("--send-every", default=30, type=int,
                        help="Envia leitura a cada N frames (padrão: 30)")
    args = parser.parse_args()

    run(
        source=args.source,
        api_url=args.api,
        api_user=args.user,
        api_pass=args.password,
        send_every=args.send_every,
    )
