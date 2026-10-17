# Operations & AWS Deployment Manual (`man.md`)

This manual covers local usage, CLI commands, and step-by-step cloud deployment of the **Warszawa Live Open Data SQL Ingestor** on **AWS (Amazon RDS for PostgreSQL + Amazon EC2 / AWS Lambda)**.

---

## 1. Datasets & Refresh Schedule

The ingestor reads the catalogue URLs from `dane.txt`, authenticates with the Warsaw Open Data REST API (`https://dane.um.warszawa.pl/api/action/...`), and persists the data into 11 PostgreSQL tables:

| Dataset Key | Schedule Group | Refresh Interval | Strategy | Target Tables |
|---|---|---|---|---|
| `weather` | `fast` | **10 minutes** | Append history (`ON CONFLICT DO NOTHING`) | `weather_measurements` |
| `air_quality` | `fast` | **10 minutes** | Upsert stations + append measurement history | `air_quality_stations`, `air_quality_measurements` |
| `tourist_routes` | `slow` | **2 hours** | Upsert by route title & point ID | `tourist_routes`, `tourist_points` |
| `toilets` | `slow` | **2 hours** | Upsert by `(lokalizacja, lon, lat)` | `toilets` |
| `defibrillators` | `slow` | **2 hours** | Upsert by `defibrillator_id` | `defibrillators` |
| `sports_activities` | `slow` | **2 hours** | Upsert by `url` | `sports_activities` |
| `open_sports_fields` | `slow` | **2 hours** | Upsert by school/address/type/equipment | `open_sports_fields` |
| `city_events` | `slow` | **2 hours** | Upsert by `url` (extracts `lat`, `lon`, `district`) | `city_events` |
| *(Audit Log)* | — | Every sync | Append run status and record count | `sync_logs` |

---

## 2. Local Development Quick Reference

### Start Local PostgreSQL (Docker)
```bash
docker compose up -d
```
- **JDBC URL (for DataGrip):** `jdbc:postgresql://localhost:5432/warszawa_live`
- **User:** `warszawa`
- **Password:** `warszawa_password`
- **Database:** `warszawa_live`

### CLI Usage
```bash
# Install dependencies in virtual environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Initialize database schema only
.venv/bin/python -m src.main --init-only

# Run one-off full synchronization of all 8 datasets
.venv/bin/python -m src.main

# Run one-off synchronization of a specific group (fast = 10m datasets, slow = 2h datasets)
.venv/bin/python -m src.main --group fast
.venv/bin/python -m src.main --group slow

# Run one-off synchronization of a single dataset
.venv/bin/python -m src.main --dataset weather

# Run continuous scheduler (weather & air_quality every 10m, others every 2h)
.venv/bin/python -m src.main --watch
```

### Run Verification & Tests
```bash
.venv/bin/flake8 src tests
.venv/bin/mypy src tests
.venv/bin/python -m pytest -v
```

---

## 3. Step-by-Step AWS Deployment Guide (RDS PostgreSQL + EC2)

We deploy the project in **3 stages** using the AWS Management Console:
1. **Stage 1:** Create a managed PostgreSQL database in **Amazon RDS** (no container required).
2. **Stage 2:** Launch an **Amazon EC2** instance (Free Tier) and link it to RDS.
3. **Stage 3:** Clone the repository on EC2 and run the continuous scheduler (`--watch`) as a `systemd` service 24/7.

---

### Stage 1: Create the PostgreSQL Database in Amazon RDS

1. Sign in to the **[AWS Management Console](https://console.aws.amazon.com/)**.
2. In the top-right corner, select the region closest to Poland: **Europe (Frankfurt) `eu-central-1`**.
3. In the top search bar, type **`RDS`**, open **Aurora and RDS**, and click **Create database**.
4. Configure the database form:
   - **Choose a database creation method:** Select **Standard create**.
   - **Engine options:**
     - **Engine type:** Select **PostgreSQL**.
     - **Engine Version:** Keep the default latest version (e.g., *PostgreSQL 16.x*).
   - **Templates:** Select **Free tier** *(automatically selects a single-AZ micro instance eligible for the AWS Free Tier)*.
   - **Settings:**
     - **DB instance identifier:** `warszawa-db`
     - **Master username:** `warszawa`
     - **Credentials management:** Select **Self managed** *(important: do not leave "Managed in AWS Secrets Manager" checked if you want to avoid extra Secrets Manager costs)*.
     - **Master password:** Enter a strong password and save it for later (`DB_PASSWORD`).
   - **Instance configuration:**
     - Leave the default **Burstable classes** (`db.t3.micro` or `db.t4g.micro`).
   - **Storage:**
     - **Allocated storage:** `20` GiB.
     - Uncheck **Enable storage autoscaling** *(prevents unexpected storage billing)*.
   - **Connectivity:**
     - **Compute resource:** Keep **Don’t connect to an EC2 compute resource** *(we will connect EC2 in Stage 2)*.
     - **Public access:**
       - Choose **Yes** if you also want to inspect the RDS database directly from your laptop via **DataGrip**.
       - Choose **No** if only the EC2 server should access the database.
   - **Database authentication:** Keep **Password authentication**.
   - **Monitoring:** Uncheck **Enable Performance Insights** (optional, avoids extra charges).
   - **Additional configuration** *(expand this section at the bottom!)*:
     - **Initial database name:** Enter **`warszawa_live`** *(critical: ensures RDS creates the `warszawa_live` database automatically on startup)*.
     - **Backup:** Optionally reduce *Backup retention period* to `1 day` or `0 days` for MVP.
5. Click **Create database** at the bottom.

Wait ~5 minutes until the `warszawa-db` status changes to **Available**. Once available, click on `warszawa-db` and copy the **Endpoint** under *Connectivity & security* (it looks like `warszawa-db.xxxx.eu-central-1.rds.amazonaws.com`).

---

### Stage 2: Launch an EC2 Instance & Link It to RDS

1. In the AWS Console top search bar, type **`EC2`**, open **EC2**, and click **Launch instance**.
2. Configure the instance:
   - **Name:** `warszawa-ingestor`
   - **Application and OS Images (Amazon Machine Image):** Select **Ubuntu** → *Ubuntu Server 24.04 LTS (HVM), SSD Volume Type* (Free tier eligible).
   - **Instance type:** Select **`t3.micro`** or **`t2.micro`** (Free tier eligible).
   - **Key pair (login):** Click **Create new key pair**, name it `warszawa-key`, select `RSA` and `.pem`, and click **Create key pair** (save the downloaded `warszawa-key.pem` file).
   - **Network settings:** Keep default VPC and allow **SSH traffic from My IP**.
3. Click **Launch instance**.
4. **Connect EC2 to RDS with one click:**
   - Go back to **RDS** → **Databases** → click on **`warszawa-db`**.
   - In the **Connectivity & security** tab (or **Actions** menu in the top-right), click **Set up EC2 connection**.
   - Select your **`warszawa-ingestor`** EC2 instance and confirm. AWS will automatically configure the Security Groups so EC2 can talk to RDS on port `5432`.
   - *(Optional for DataGrip)*: If you enabled **Public access** in Stage 1 and want to connect from DataGrip on your Mac, click the **VPC security group** link under RDS *Connectivity & security*, go to **Edit inbound rules**, and add a rule: Type `PostgreSQL` (port `5432`), Source `My IP`.

---

### Stage 3: Deploy the Application & Enable 24/7 `systemd` Service on EC2

1. Connect to your EC2 instance (either click **Connect** → **EC2 Instance Connect** in the browser, or via SSH from your terminal):
   ```bash
   chmod 400 ~/Downloads/warszawa-key.pem
   ssh -i ~/Downloads/warszawa-key.pem ubuntu@<EC2-PUBLIC-IPV4>
   ```
2. Install Python 3 venv and Git on Ubuntu:
   ```bash
   sudo apt update && sudo apt install -y python3-venv python3-pip git
   ```
3. Clone the repository (branch `postgre-aws`) and set up the virtual environment:
   ```bash
   git clone -b postgre-aws https://github.com/k-bar/whatever.git ~/whatever
   cd ~/whatever
   python3 -m venv .venv
   .venv/bin/pip install --upgrade pip
   .venv/bin/pip install -r requirements.txt
   ```
4. Create an environment configuration file `/home/ubuntu/whatever/.env.aws` with your RDS endpoint and Warsaw API key (restrict its permissions with `chmod 600`):
   ```bash
   cat << 'EOF' > ~/whatever/.env.aws
   DB_HOST=warszawa-db.xxxx.eu-central-1.rds.amazonaws.com
   DB_PORT=5432
   DB_NAME=warszawa_live
   DB_USER=warszawa
   DB_PASSWORD=YOUR_RDS_PASSWORD
   DB_SSLMODE=require
   WARSZAWA_API_TOKEN=YOUR_WARSZAWA_API_TOKEN
   EOF
   chmod 600 ~/whatever/.env.aws
   ```
5. Test the connection and run an initial synchronization:
   ```bash
   set -a && source ~/whatever/.env.aws && set +a
   ~/whatever/.venv/bin/python -m src.main
   ```
6. Configure a **`systemd` service** so the `--watch` scheduler runs 24/7 in the background and restarts automatically if the server reboots:
   ```bash
   sudo tee /etc/systemd/system/warszawa-ingestor.service > /dev/null << 'EOF'
   [Unit]
   Description=Warszawa Open Data PostgreSQL Ingestor Scheduler
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/whatever
   EnvironmentFile=/home/ubuntu/whatever/.env.aws
   ExecStart=/home/ubuntu/whatever/.venv/bin/python -m src.main --watch
   Restart=always
   RestartSec=15

   [Install]
   WantedBy=multi-user.target
   EOF
   ```
7. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now warszawa-ingestor.service
   ```
8. Check service status and live logs:
   ```bash
   sudo systemctl status warszawa-ingestor.service
   journalctl -u warszawa-ingestor.service -f
   ```

---

## 4. Alternative Serverless Deployment (AWS Lambda + EventBridge)

If you prefer not to run an EC2 instance 24/7, `src/scheduler.py` provides a built-in AWS Lambda handler:
- **Handler:** `src.scheduler.lambda_handler`
- **Environment variables:** `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE=require`, `WARSZAWA_API_TOKEN`
- **Amazon EventBridge Schedules:**
  1. **Fast schedule (`rate(10 minutes)`):** Target Lambda with JSON input `{"group": "fast"}` (syncs `weather` and `air_quality`).
  2. **Slow schedule (`rate(2 hours)`):** Target Lambda with JSON input `{"group": "slow"}` (syncs the remaining 6 datasets).
