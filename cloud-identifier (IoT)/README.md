# ☁️ Cloud Pattern Identifier

Sistema de visão computacional que identifica padrões de nuvens em tempo real a partir de webcam ou vídeo, com foco em imagens do tipo ISS/satélite.

---

## Descrição da solução

O programa captura frames de vídeo e executa um pipeline de análise que classifica as nuvens visíveis em cinco categorias:

| Classe | Características detectadas |
|---|---|
| **Cumulonimbus** | Alta cobertura escura, textura rugosa — indica tempestade |
| **Cumulus** | Bordas bem definidas, alta densidade de bordas Sobel |
| **Stratus** | Camada uniforme, baixa textura, alta cobertura |
| **Cirrus** | Alta altitude, bordas esparsas, baixa densidade |
| **Clear Sky** | Cobertura mínima de nuvens |

### Pipeline de visão computacional

```
Frame → Segmentação HSV + Threshold Adaptativo
      → Morfologia (open/close)
      → Análise de textura (Laplaciano)
      → Análise de bordas (Sobel)
      → Classificação por regras heurísticas
      → Bounding Boxes + HUD na tela
```

---

## Bibliotecas utilizadas

- **OpenCV** (`opencv-python`) — captura de vídeo, processamento de imagem, segmentação, morfologia, renderização
- **NumPy** — operações matriciais e métricas estatísticas

---

## Instruções de execução

### 1. Instale as dependências

```bash
pip install -r requirements.txt
```

### 2. Execute com webcam (padrão)

```bash
python src/cloud_identifier.py
```

### 3. Execute com arquivo de vídeo

```bash
python src/cloud_identifier.py caminho/para/video.mp4
```

> Recomendado: vídeos ISS disponíveis gratuitamente em https://eol.jsc.nasa.gov

### 4. Controles durante a execução

| Tecla | Ação |
|---|---|
| `Q` ou `ESC` | Sair |
| `S` | Salvar frame atual em `/output` |
| `M` | Alternar entre vídeo normal e máscara de segmentação |

---

## Estrutura do projeto

```
cloud-identifier/
├── src/
│   └── cloud_identifier.py   # Pipeline principal
├── output/                   # Frames salvos pelo usuário
├── requirements.txt
└── README.md
```

---

## Integrantes

- **Gustavo Bonani Favero Marcos** — RM553493
- **Gustavo Manganelli Felex** — RM554242
- **Vinicius Issa Gois** — RM553814
- **Vinicius Caetano dos Santos** — RM552904
- **Wesley Leopoldino do Nascimento Vieira** — RM553496

---

## Contexto GS

A identificação automática de padrões de nuvens tem aplicação direta em monitoramento climático e alertas de desastres naturais. Com câmeras instaladas em drones, satélites ou estações meteorológicas, o sistema pode detectar formações de cumulonimbus associadas a tempestades severas, auxiliando na emissão de alertas preventivos em regiões vulneráveis.
