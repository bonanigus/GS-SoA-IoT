# ☁️ Cloud Identifier — API & Dashboard

Sistema de identificação de padrões de nuvens via Visão Computacional (OpenCV), integrado com API REST, banco de dados e autenticação JWT.

---

## Motivação

Identificação automática de formações de nuvens tem aplicação direta em **alertas de desastres naturais** — especialmente na detecção precoce de cumulonimbus associados a tempestades severas. O sistema combina o pipeline de CV (vídeo/webcam) com uma API que persiste histórico, emite alertas automáticos e serve um dashboard em tempo real.

---

## Arquitetura

```
cloud-dashboard/
├── main.py                          # Entry point FastAPI
├── app/
│   ├── models/
│   │   ├── domain.py                # POO: Sensor, CloudSensor, Alert (classes abstratas, herança, polimorfismo)
│   │   └── orm.py                   # Entidades SQLAlchemy (SatelliteORM, SensorORM, etc.)
│   ├── schemas/
│   │   └── schemas.py               # DTOs Pydantic (request/response)
│   ├── repositories/
│   │   └── repositories.py          # Interfaces + implementações (ISensorRepository, etc.)
│   ├── services/
│   │   └── service.py               # Lógica de negócio (CloudIdentifierService)
│   ├── routers/
│   │   └── routers.py               # Endpoints REST (auth, satellites, sensors, readings, alerts, dashboard)
│   └── core/
│       ├── database.py              # SQLAlchemy engine + sessão + DI
│       └── security.py             # JWT, hashing, autenticação
└── requirements.txt
```

---

## Critérios atendidos

| Critério | Implementação |
|---|---|
| **POO — Classes Abstratas** | `Sensor`, `Alert` em `domain.py` |
| **Herança e Polimorfismo** | `CloudSensor`, `TemperatureSensor`, `StormAlert`, `SensorOfflineAlert` |
| **Classes Públicas, Estáticas, Privadas** | `_id`, `__created_at`, `CloudSensor._instance_count`, `Satellite.iss()` |
| **Interfaces e DI** | `ISatelliteRepository`, `ISensorRepository`, `IReadingRepository`, `IAlertRepository` |
| **Value Objects / DTOs** | `Coordinates`, `CloudReading` (VOs imutáveis); schemas Pydantic (DTOs) |
| **Tratamento de Exceções** | `try/except` em todos os endpoints; validações em VOs e DTOs |
| **DateTime / histórico** | `timestamp` indexado; queries `get_since()`, `get_readings_since()` |
| **Banco de Dados** | SQLite via SQLAlchemy; 5 tabelas; seed automático |
| **WebService / API REST** | FastAPI com 6 grupos de endpoints |
| **Autenticação JWT** | Bearer token; `get_current_user`, `get_admin_user` |
| **CORS** | `CORSMiddleware` configurado em `main.py` |
| **Swagger automático** | `/docs` (Swagger UI) e `/redoc` |
| **Estrutura de pastas** | Separação por camada: models / schemas / repositories / services / routers / core |

---

## Bibliotecas utilizadas

- **FastAPI** — framework web e geração automática de Swagger
- **SQLAlchemy** — ORM e acesso ao banco SQLite
- **Pydantic v2** — validação de dados e DTOs
- **python-jose** — criação e verificação de JWT
- **passlib[bcrypt]** — hashing de senhas
- **OpenCV** — pipeline de visão computacional (módulo `cloud_identifier.py`)
- **NumPy** — operações matriciais

---

## Como executar

### 1. Instale as dependências

```bash
pip install -r requirements.txt
```

### 2. Inicie a API

```bash
uvicorn main:app --reload
```

A API estará disponível em `http://localhost:8000`.

### 3. Acesse a documentação Swagger

```
http://localhost:8000/docs
```

### 4. Credenciais padrão (seed automático)

| Campo | Valor |
|---|---|
| username | `admin` |
| password | `admin123` |

### 5. Exemplo de uso via curl

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Dashboard summary
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/dashboard/summary

# Ingerir leitura do pipeline CV
curl -X POST http://localhost:8000/readings/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sensor_id":"<id>","cloud_class":"Cumulonimbus","confidence":0.88,"coverage":0.72,"texture_score":28.5,"edge_density":0.09}'
```

---

## Integração com o pipeline OpenCV

O script `cloud_identifier.py` pode enviar leituras para a API em tempo real:

```python
import requests, cv2
# ... após classificar o frame:
requests.post("http://localhost:8000/readings/",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "sensor_id": SENSOR_ID,
        "cloud_class": analysis.cloud_class,
        "confidence": analysis.confidence,
        "coverage": analysis.coverage,
        "texture_score": analysis.texture_score,
        "edge_density": analysis.edge_density,
    }
)
```

---

## Endpoints principais

| Método | Rota | Descrição |
|---|---|---|
| POST | `/auth/login` | Login → JWT |
| POST | `/auth/register` | Cadastro de usuário |
| GET | `/dashboard/summary` | Resumo para o dashboard |
| GET | `/satellites/` | Lista satélites |
| GET | `/sensors/` | Lista sensores |
| POST | `/readings/` | Ingere leitura do CV |
| GET | `/readings/recent` | Últimas leituras |
| GET | `/alerts/` | Alertas ativos |
| PATCH | `/alerts/resolve` | Resolve um alerta |

---

## Diagrama de fluxo

```
[Webcam/Vídeo]
      │
      ▼
[cloud_identifier.py — Pipeline OpenCV]
  Segmentação HSV → Morfologia → Textura → Bordas → Classificação
      │
      ▼
[POST /readings/]  ◄── JWT Bearer Token
      │
      ▼
[CloudIdentifierService]
  .ingest_reading()
      ├── ReadingRepository.create()  →  cloud_readings (SQLite)
      └── is_storm_risk? → AlertRepository.create() → alerts (SQLite)
      │
      ▼
[GET /dashboard/summary]
  total_sensors | readings_24h | active_alerts | class_distribution
      │
      ▼
[Dashboard / Frontend]
```

---

## Integrantes

- **Gustavo Bonani Favero Marcos** — RM553493
- **Gustavo Manganelli Felex** — RM554242
- **Vinicius Issa Gois** — RM553814
- **Vinicius Caetano dos Santos** — RM552904
- **Wesley Leopoldino do Nascimento Vieira** — RM553496

---

## Evidências de execução

Para gerar as evidências, execute a API (`uvicorn main:app --reload`) e acesse:

- `http://localhost:8000/docs` → screenshot do Swagger com todos os endpoints
- `http://localhost:8000/dashboard/summary` → JSON com dados ao vivo
- Execute `cloud_identifier.py` com um vídeo ISS e demonstre leituras chegando em tempo real

