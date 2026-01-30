# Microservices Migration

Kompletny przewodnik migracji aplikacji monolitycznej do architektury mikroserwisów z wdrożeniem na Kubernetes.

---

## Spis treści

1. [Przygotowanie Środowiska i Monolitu](#1-przygotowanie-środowiska-i-monolitu)
2. [Migracja do Docker Compose](#2-migracja-do-docker-compose)
3. [Orkiestracja w Kubernetes (Minikube)](#3-orkiestracja-w-kubernetes-minikube)
4. [Rozwiązywanie Problemów](#4-rozwiązywanie-problemów)

---

## 1. Przygotowanie Środowiska i Monolitu

### Krok 1: Generowanie kluczy bezpieczeństwa

Wszystkie serwisy muszą używać tego samego klucza do poprawnej weryfikacji tokenów JWT.

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Wynik:** `oxtcpUJ6T1jeooAn-MElGPjkv1Ex6jLCGquep_WxpsQ` (przykład)

Kopiujemy wygenerowany klucz i dodajemy jako `SECRET_KEY` do plików `.env`:
- `./monolite/.env`
- `./microservices/auth-service/.env`

---

### Krok 2: Uruchomienie tymczasowej bazy danych (Dev)

Uruchamiamy instancję PostgreSQL, która posłuży jako źródło danych dla monolitu.

```sh
docker run -d `
  --name postgres-dev `
  -e POSTGRES_DB=project_db `
  -e POSTGRES_USER=admin `
  -e POSTGRES_PASSWORD=password123 `
  -p 5432:5432 `
  postgres:16-alpine
```

Dodajemy `DATABASE_URL` do pliku `.env`:
- `./monolite/.env`

```bash
DATABASE_URL=postgresql+psycopg://admin:password123@localhost:5432/project_db
```

---

### Krok 3: Uruchomienie i testowanie Monolitu

```sh
cd ./monolite
uv sync
uv pip install -r requirements.txt
uv run uvicorn main:app --reload
```

**Testowanie:**
1. Otwieramy przeglądarkę: `http://localhost:8000`
2. Rejestrujemy nowego użytkownika
3. Dodajemy kilka notatek

> **Uwaga:** Dane te będą później migrowane do mikroserwisów.

---

## 2. Migracja do Docker Compose

### Krok 4: Eksport danych (Dump)

Wykonujemy kopię zapasową bazy danych monolitu.

```sh
# Z folderu /microservices
docker exec postgres-dev pg_dump -U admin project_db > backup.sql
```

---

### Krok 5: Konfiguracja środowiska Docker Compose

Tworzymy plik `./microservices/.env`:

```bash
DB_USER=admin
DB_PASSWORD=password123
DB_NAME=microservices
SECRET_KEY=oxtcpUJ6T1jeooAn-MElGPjkv1Ex6jLCGquep_WxpsQ
```

Tworzymy oraz wypełniamy pliki `.env` serwisów:

**`./microservices/auth-service/.env`:**
```bash
SECRET_KEY=oxtcpUJ6T1jeooAn-MElGPjkv1Ex6jLCGquep_WxpsQ
DATABASE_URL=postgresql+asyncpg://admin:password123@postgres:5432/microservices
```

**`./microservices/notes-service/.env`:**
```bash
DATABASE_URL=postgresql+asyncpg://admin:password123@postgres:5432/microservices
```

---

### Krok 6: Czyszczenie i restart bazy danych

```sh
# Usuwamy starą bazę
docker rm -f postgres-dev

# Usuwamy stare volumey Docker Compose (jeśli istnieją)
docker volume rm microservices_postgres-data

# Uruchamiamy nowy PostgreSQL ze środowiska docker-compose
docker-compose up -d postgres
```

---

### Krok 7: Uruchomienie mikroserwisów

```sh
# Uruchamiamy wszystkie serwisy
docker-compose up -d

# Sprawdzamy status
docker-compose ps

```

---

### Krok 8: Restauracja danych w nowej bazie

```sh
# Ładujemy dump
cat backup.sql | docker exec -i postgres psql -U admin -d microservices

# Weryfikacja
docker exec postgres psql -U admin -d microservices -c "SELECT * FROM users;"
```

**Oczekiwany wynik:** Lista użytkowników z monolitu.

**Testowanie:**
1. Otwieramy `index.html` z folderu monolitu
2. Logujemy się używając danych z monolitu
3. Notatki muszą być widoczne

---

## 3. Orkiestracja w Kubernetes (Minikube)

### Krok 9: Przygotowanie klastra

```sh
# Uruchamiamy Minikube
minikube start --driver=docker --cpus=4 --memory=4096
```

```sh
# Ustawiamy Docker environment na Minikube (w git bash konsoli)
eval $(minikube docker-env)
```

---

### Krok 10: Budowanie obrazów Docker

**WAŻNE:** Obrazy muszą być zbudowane wewnąrz Minikube

```sh
cd microservices

# Budujemy obrazy
docker build --no-cache -t auth-service ./auth-service
docker build --no-cache -t notes-service ./notes-service
docker build --no-cache -t api-gateway ./api-gateway

# Weryfikacja
docker images | Select-String "auth-service|notes-service|api-gateway"
```

---

### Krok 11: Konfiguracja Sekretów i ConfigMap

Uzupełniamy plik `./microservices/minikube/secrets.yml` wklejając nowy SECRET_KEY:

```yaml
...
stringData:
  SECRET_KEY: "oxtcpUJ6T1jeooAn-MElGPjkv1Ex6jLCGquep_WxpsQ"
...
```

---

### Krok 12: Wdrożenie infrastruktury

```sh
cd minikube

# Apply w kolejności
kubectl apply -f secrets.yml
kubectl apply -f volumes.yml
kubectl apply -f postgres-deployment.yml

# Weryfikacja
kubectl get pods
```

---

### Krok 13: Wdrożenie serwisów aplikacji

```sh
# Deploy auth-service
kubectl apply -f auth-deployment.yml

# Deploy notes-service
kubectl apply -f notes-deployment.yml

# Deploy api-gateway
kubectl apply -f gateway-deployment.yml

# Sprawdzamy status
kubectl get pods
```

**Czekamy aż wszystkie pody będą w stanie `Running` i `1/1 READY`.**

---

### Krok 14: Migracja danych do Kubernetes

Przenosimy dane z dumpu do bazy w klastrze Kubernetes.

```sh
# Dostajemy nazwę podu PostgreSQL
kubectl get pods -l app=postgres

#NAME                        READY   STATUS    RESTARTS   AGE
#postgres-54fd9cb4cd-gfzkz   1/1     Running   0          5m34s

# Ładujemy dump
cat ../backup.sql | kubectl exec -i postgres-54fd9cb4cd-gfzkz -- psql -U admin -d microservices

# Weryfikacja
kubectl exec -i postgres-54fd9cb4cd-gfzkz -- psql -U admin -d microservices -c "SELECT * FROM users;"
```

**Oczekiwany wynik:** Lista użytkowników z monolitu.

---

### Krok 15: Udostępnienie aplikacji

Aby aplikacja WWW (`index.html`) mogła połączyć się z API, wystawiamy Bramę API na zewnątrz:

**Port Forwarding (dla development)**
```sh
kubectl port-forward service/api-gateway 8000:8000
```

**Testowanie:**
1. Otwieramy `index.html`
2. Łogujemy się używając danych z monolitu
3. Sprawdzamy czy wszystkie funkcje działają oraz czy są notatki z poprzedniej bazy

---

## Przydatne komendy

### Docker Compose
```sh
docker-compose ps                    # Status serwisów
docker-compose logs -f <service>     # Logi
docker-compose restart <service>     # Restart
docker-compose down                  # Zatrzymaj wszystko
```

### Kubernetes
```sh
kubectl get pods                     # Lista podów
kubectl get svc                      # Lista serwisów
kubectl logs <pod-name> -f           # Logi
kubectl describe pod <pod-name>      # Szczegóły podu
kubectl exec -it <pod-name> -- sh    # Wejdź do kontenera
kubectl delete pod <pod-name>        # Restart podu
```

---

## Architektura finalna

```
┌─────────────┐
│   Browser   │
│ (index.html)│
└──────┬──────┘
       │
       │ HTTP :8000
       ▼
┌─────────────────┐
│   API Gateway   │
│   (port 8000)   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌─────────┐ ┌──────────┐
│  Auth   │ │  Notes   │
│ Service │ │ Service  │
│  :8001  │ │  :8002   │
└────┬────┘ └────┬─────┘
     │           │
     └─────┬─────┘
           │
           ▼
    ┌──────────────┐
    │  PostgreSQL  │
    │   :5432      │
    └──────────────┘
```