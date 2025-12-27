# Area51 API Services

A Django-based API services for the Area51 casino.

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python      | 3.8+    |
| PostgreSQL  | 13.10   |
| Docker      | Latest  |

> **Note:** If using Ubuntu, version 20.04 is recommended for best compatibility.

---

## Installation

### 1. Install System Dependencies (Ubuntu/Debian)

```bash
sudo apt-get update && sudo apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libjpeg-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libtiff-dev \
    libwebp-dev \
    python3-dev \
    python3-setuptools \
    python3-wheel \
    gettext \
    libcurl4-openssl-dev \
    pkg-config \
    libharfbuzz-dev \
    libfribidi-dev \
    libopenjp2-7-dev \
    libyaml-dev
```

### 2. Clone the Repository

```bash
git clone https://github.com/RevolutionDigital1/area51_apiservices.git
cd area51_apiservices
```

### 3. Set Up the Database

Start the Docker containers:

```bash
docker compose up -d
```

#### Import Development Data

1. **Export data from source** (if creating a new backup):
   ```bash
   pg_dump -U "$DB_USER" -p "$DB_PORT" -h "$DB_HOST" -F p "$DB_NAME" | gzip > develop_db.sql.gz
   ```

2. **Copy the backup to the container:**
   ```bash
   docker cp develop_db.sql.gz postgres_area51:/tmp/develop_db.sql.gz
   ```

3. **Restore the database:**
   ```bash
   docker exec -it postgres_area51 sh -c "
       cd /tmp && \
       gunzip develop_db.sql.gz && \
       psql -U \$DB_USER -d develop_db -f develop_db.sql && \ # replace the user here and the db here
       rm develop_db.sql
   "
   ```

### 4. Set Up Python Environment

Create and activate a virtual environment:

```bash
pip install virtualenv
virtualenv .env
source .env/bin/activate
```

> **Windows:** Use `.env\Scripts\activate` instead.

Install dependencies:

```bash
pip install --upgrade setuptools  # Optional but recommended
pip install -r requirements.txt
```

### 5. Configure Environment Variables

Create a `.env` file in the project root based on `.env.example`:

```bash
cp .env.example .env
```

Edit the `.env` file with your configuration values.

### 6. Sync migrations

```bash
python manage.py makemigrations users casino
    bets payments admin_panel acuitytec # These are all the current apps at the time
# You may need to change this apps for a better fit
python manage.py migrate --fake
```

### 8. Run the Development Server

```bash
python manage.py runserver
```

The application will be available at **http://127.0.0.1:8000**
