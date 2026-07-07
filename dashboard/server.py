"""
RetailFlow Dashboard Server v3 — Full Infrastructure + Pipeline Control
Starts Docker containers, provisions S3 via Terraform, applies DB schema,
and runs the full ETL pipeline — all from a single "Start Pipeline" button.
"""
import json
import os
import re
import socket
import subprocess
import threading
import time
from datetime import datetime
from werkzeug.utils import secure_filename

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import boto3

app = Flask(__name__, static_folder="static")
CORS(app)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── DB / S3 Config ─────────────────────────────────────────────────────────────
DB_CONFIG = dict(host="localhost", port=5433, dbname="retailflow_dw",
                 user="postgres", password="postgres")
S3_CONFIG  = dict(endpoint_url="http://localhost:4566",
                  aws_access_key_id="mock", aws_secret_access_key="mock",
                  region_name="us-east-1")
RAW_BUCKET     = "retailflow-raw"
CURATED_BUCKET = "retailflow-curated"

# ── Pipeline State ─────────────────────────────────────────────────────────────
_pipeline_lock = threading.Lock()
_pipeline_proc = None
_stop_event    = threading.Event()

# 5 steps now: infra boot, then the 4 ETL steps
STEP_KEYS = ["infra", "ingestion", "validation", "transform", "load"]
ETL_STEP_MARKERS = [
    ("[Step 1/4]", "ingestion"),
    ("[Step 2/4]", "validation"),
    ("[Step 3/4]", "transform"),
    ("[Step 4/4]", "load"),
]

def _fresh_step():
    return {"status": "idle", "started": None, "ended": None, "message": ""}

pipeline_state = {
    "status":       "idle",
    "current_step": None,
    "steps":        {k: _fresh_step() for k in STEP_KEYS},
    "log":          [],
    "target_date":  "2026-07-01",
    "started_at":   None,
    "ended_at":     None,
    "error":        None,
}

def _ts():
    return datetime.now().strftime("%H:%M:%S")

def _log(msg):
    with _pipeline_lock:
        pipeline_state["log"].append(f"[{_ts()}] {msg}")
        if len(pipeline_state["log"]) > 600:
            pipeline_state["log"] = pipeline_state["log"][-400:]


# ── Infrastructure Bootstrap ──────────────────────────────────────────────────
def _port_open(host, port, timeout=2):
    try:
        s = socket.create_connection((host, port), timeout)
        s.close()
        return True
    except:
        return False


def _ensure_docker_daemon_running():
    """Check if docker daemon is responsive; if not, try to launch Docker Desktop."""
    _log("Checking if Docker daemon is running...")
    # Test connection
    res = subprocess.run(["docker", "info"], capture_output=True)
    if res.returncode == 0:
        _log("Docker daemon is running and responsive.")
        return True

    # Daemon not running, try launching Docker Desktop on Windows
    docker_desktop_path = "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe"
    if os.path.exists(docker_desktop_path):
        _log("Docker daemon is offline. Starting Docker Desktop application...")
        try:
            subprocess.Popen([docker_desktop_path])
            # Wait up to 60 seconds
            for i in range(30):
                if _stop_event.is_set():
                    return False
                time.sleep(2)
                res = subprocess.run(["docker", "info"], capture_output=True)
                if res.returncode == 0:
                    _log("Docker Desktop daemon has successfully started and is responding!")
                    return True
                if i % 5 == 4:
                    _log(f"  Waiting for Docker Desktop daemon... ({(i+1)*2}s)")
            else:
                _log("WARNING: Docker Desktop was started but daemon did not respond within 60s.")
        except Exception as e:
            _log(f"WARNING: Could not start Docker Desktop application: {e}")
    else:
        _log("WARNING: Docker Desktop executable not found at typical path. Please start Docker manually.")
    
    return False


def _containers_already_running():
    """Return True if both LocalStack and Postgres containers are already up and healthy."""
    ls_ok = _port_open("127.0.0.1", 4566)
    pg_ok = _port_open("127.0.0.1", 5433)
    if ls_ok and pg_ok:
        try:
            conn = psycopg2.connect(**DB_CONFIG, connect_timeout=3)
            conn.close()
            return True
        except Exception:
            pass
    return False


def _s3_buckets_exist():
    """Return True if both S3 buckets already exist in LocalStack."""
    try:
        s3 = get_s3()
        s3.head_bucket(Bucket=RAW_BUCKET)
        s3.head_bucket(Bucket=CURATED_BUCKET)
        return True
    except Exception:
        return False


def _schema_tables_exist():
    """Return True if the warehouse tables are already present in Postgres."""
    try:
        conn = psycopg2.connect(**DB_CONFIG, connect_timeout=3)
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('fact_orders','dim_customer','dim_product','dim_date')
        """)
        count = cur.fetchone()[0]
        conn.close()
        return count == 4
    except Exception:
        return False


def _boot_infrastructure():
    """Start Docker containers, wait for health, run Terraform, apply schema.
    Skips each sub-step intelligently if it's already done to save time on re-runs.
    """
    with _pipeline_lock:
        pipeline_state["steps"]["infra"]["status"] = "running"
        pipeline_state["steps"]["infra"]["started"] = datetime.now().isoformat()
        pipeline_state["current_step"] = "infra"

    # ── 0. Docker daemon check ────────────────────────────────────────────────
    _ensure_docker_daemon_running()
    if _stop_event.is_set():
        return False

    # ── 1. Docker compose up — skip if containers are already healthy ─────────
    if _containers_already_running():
        _log("Containers already running — skipping docker compose up.")
    else:
        _log("Starting Docker containers (LocalStack S3 + PostgreSQL)...")
        try:
            result = subprocess.run(
                ["docker", "compose", "up", "-d"],
                cwd=PROJECT_ROOT,
                capture_output=True, text=True, timeout=120
            )
            for line in (result.stdout + result.stderr).strip().split("\n"):
                if line.strip():
                    _log(f"  docker: {line.strip()}")
            if result.returncode != 0:
                raise RuntimeError(f"docker compose up failed: {result.stderr}")
        except FileNotFoundError:
            _log("ERROR: 'docker' command not found. Is Docker Desktop installed?")
            raise RuntimeError("Docker not found")

        if _stop_event.is_set():
            return False

        # Wait for LocalStack S3 (port 4566)
        _log("Waiting for LocalStack S3 to become healthy...")
        for i in range(45):
            if _stop_event.is_set():
                return False
            if _port_open("127.0.0.1", 4566):
                _log("LocalStack S3 is ready!")
                break
            time.sleep(2)
            if i % 3 == 2:
                _log(f"  Still waiting for LocalStack... ({(i+1)*2}s)")
        else:
            raise RuntimeError("LocalStack did not start in time")

        # Wait for PostgreSQL (port 5433)
        _log("Waiting for PostgreSQL to become healthy...")
        for i in range(30):
            if _stop_event.is_set():
                return False
            if _port_open("127.0.0.1", 5433):
                time.sleep(1)
                try:
                    conn = psycopg2.connect(**DB_CONFIG)
                    conn.close()
                    _log("PostgreSQL is ready and accepting connections!")
                    break
                except Exception:
                    pass
            time.sleep(2)
            if i % 3 == 2:
                _log(f"  Still waiting for Postgres... ({(i+1)*2}s)")
        else:
            raise RuntimeError("PostgreSQL did not start in time")

    if _stop_event.is_set():
        return False

    # ── 2. Terraform — skip init if .terraform dir already exists ─────────────
    tf_path = os.path.join(PROJECT_ROOT, "bin", "terraform.exe")
    infra_dir = os.path.join(PROJECT_ROOT, "infra")

    if _s3_buckets_exist():
        _log("S3 buckets already exist — skipping Terraform provisioning.")
    elif os.path.exists(tf_path):
        _log("Provisioning S3 buckets via Terraform...")
        tf_initialized = os.path.isdir(os.path.join(infra_dir, ".terraform"))

        if not tf_initialized:
            _log("  Running terraform init...")
            r = subprocess.run(
                [tf_path, "init", "-input=false"],
                cwd=infra_dir, capture_output=True, text=True, timeout=120
            )
            for line in r.stdout.strip().split("\n"):
                if line.strip() and any(k in line for k in ("Initializing", "installed", "configured")):
                    _log(f"  terraform: {line.strip()}")
        else:
            _log("  Terraform already initialized — skipping init.")

        r = subprocess.run(
            [tf_path, "apply", "-auto-approve", "-input=false"],
            cwd=infra_dir, capture_output=True, text=True, timeout=120
        )
        for line in r.stdout.strip().split("\n"):
            if line.strip() and any(k in line for k in ("Apply", "created", "complete", "No changes")):
                _log(f"  terraform: {line.strip()}")
        if r.returncode != 0:
            _log(f"  terraform stderr: {r.stderr.strip()}")
            raise RuntimeError("Terraform apply failed")
        _log("S3 buckets provisioned successfully!")
    else:
        _log("  Terraform binary not found, skipping (buckets may already exist)")

    if _stop_event.is_set():
        return False

    # ── 3. Schema DDL — skip if all 4 tables already present ─────────────────
    if _schema_tables_exist():
        _log("Warehouse schema already exists — skipping DDL.")
    else:
        _log("Applying warehouse schema (dim_customer, dim_product, dim_date, fact_orders)...")
        schema_path = os.path.join(PROJECT_ROOT, "warehouse", "schema.sql")
        if os.path.exists(schema_path):
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                cur = conn.cursor()
                with open(schema_path, "r") as f:
                    cur.execute(f.read())
                conn.commit()
                conn.close()
                _log("Database schema applied successfully!")
            except Exception as e:
                _log(f"  Schema warning: {e}")
        else:
            _log("  schema.sql not found, skipping")

    with _pipeline_lock:
        pipeline_state["steps"]["infra"]["status"] = "completed"
        pipeline_state["steps"]["infra"]["ended"] = datetime.now().isoformat()

    return True


# ── Pipeline Background Thread ─────────────────────────────────────────────────
def run_pipeline_background(target_date: str):
    global _pipeline_proc, pipeline_state
    _stop_event.clear()

    with _pipeline_lock:
        pipeline_state.update({
            "status": "running", "current_step": None, "error": None,
            "log":  [f"[{_ts()}] === RetailFlow Pipeline starting for {target_date} ==="],
            "target_date": target_date,
            "started_at": datetime.now().isoformat(), "ended_at": None,
            "steps": {k: _fresh_step() for k in STEP_KEYS},
        })

    # ── PHASE 1: Boot infrastructure ──
    try:
        ok = _boot_infrastructure()
        if not ok or _stop_event.is_set():
            with _pipeline_lock:
                pipeline_state["status"] = "stopped"
            return
    except Exception as e:
        with _pipeline_lock:
            pipeline_state["status"] = "error"
            pipeline_state["error"] = f"Infrastructure boot failed: {e}"
            pipeline_state["steps"]["infra"]["status"] = "error"
        _log(f"ERROR: {e}")
        return

    # ── PHASE 2: Run ETL pipeline script ──
    _log("Infrastructure ready. Launching ETL pipeline...")

    cmd = [
        "powershell.exe", "-ExecutionPolicy", "Bypass",
        "-File", os.path.join(PROJECT_ROOT, "scripts", "run_pipeline.ps1"),
        "-TargetDate", target_date,
    ]

    try:
        _pipeline_proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace", cwd=PROJECT_ROOT,
        )

        for raw_line in iter(_pipeline_proc.stdout.readline, ""):
            if _stop_event.is_set():
                _pipeline_proc.terminate()
                with _pipeline_lock:
                    pipeline_state["status"] = "stopped"
                    if pipeline_state["current_step"]:
                        pipeline_state["steps"][pipeline_state["current_step"]]["status"] = "stopped"
                        pipeline_state["steps"][pipeline_state["current_step"]]["ended"]  = datetime.now().isoformat()
                return

            line = raw_line.rstrip()
            _log(line)

            # Detect step transitions
            for idx, (marker, step_name) in enumerate(ETL_STEP_MARKERS):
                if marker in line:
                    with _pipeline_lock:
                        if pipeline_state["current_step"]:
                            prev = pipeline_state["current_step"]
                            if pipeline_state["steps"][prev]["status"] == "running":
                                pipeline_state["steps"][prev]["status"]  = "completed"
                                pipeline_state["steps"][prev]["ended"]   = datetime.now().isoformat()
                        pipeline_state["current_step"] = step_name
                        pipeline_state["steps"][step_name]["status"]  = "running"
                        pipeline_state["steps"][step_name]["started"] = datetime.now().isoformat()

            # Pipeline success detection
            if "Pipeline run completed successfully" in line:
                with _pipeline_lock:
                    if pipeline_state["current_step"]:
                        step = pipeline_state["current_step"]
                        pipeline_state["steps"][step]["status"] = "completed"
                        pipeline_state["steps"][step]["ended"]  = datetime.now().isoformat()
                    pipeline_state["status"]    = "completed"
                    pipeline_state["ended_at"]  = datetime.now().isoformat()

        _pipeline_proc.wait()
        with _pipeline_lock:
            if pipeline_state["status"] == "running":
                if _pipeline_proc.returncode != 0:
                    pipeline_state["status"] = "error"
                    pipeline_state["error"]  = f"Pipeline exited with code {_pipeline_proc.returncode}"
                    if pipeline_state["current_step"]:
                        pipeline_state["steps"][pipeline_state["current_step"]]["status"] = "error"
                        pipeline_state["steps"][pipeline_state["current_step"]]["ended"]  = datetime.now().isoformat()
                else:
                    pipeline_state["status"]   = "completed"
                    pipeline_state["ended_at"] = datetime.now().isoformat()
                    if pipeline_state["current_step"]:
                        pipeline_state["steps"][pipeline_state["current_step"]]["status"] = "completed"
                        pipeline_state["steps"][pipeline_state["current_step"]]["ended"]  = datetime.now().isoformat()

    except Exception as e:
        with _pipeline_lock:
            pipeline_state["status"] = "error"
            pipeline_state["error"]  = str(e)
            if pipeline_state["current_step"]:
                pipeline_state["steps"][pipeline_state["current_step"]]["status"] = "error"
                pipeline_state["steps"][pipeline_state["current_step"]]["ended"]  = datetime.now().isoformat()
        _log(f"ERROR: {e}")


# ── Helpers ────────────────────────────────────────────────────────────────────
def get_conn(): return psycopg2.connect(**DB_CONFIG)
def get_s3():   return boto3.client("s3", **S3_CONFIG)
def rows_as_dicts(cur):
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── Static / index ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/demo.html")
def demo():
    return send_from_directory("static", "demo.html")


# ── Pipeline API ───────────────────────────────────────────────────────────────
@app.route("/api/run_pipeline", methods=["POST"])
def api_run_pipeline():
    with _pipeline_lock:
        if pipeline_state["status"] == "running":
            return jsonify({"success": False, "error": "Pipeline already running"})
    data = request.get_json(silent=True) or {}
    target_date = data.get("target_date", "2026-07-01")
    threading.Thread(target=run_pipeline_background, args=(target_date,), daemon=True).start()
    return jsonify({"success": True, "message": f"Pipeline started for {target_date}"})

@app.route("/api/stop_pipeline", methods=["POST"])
def api_stop_pipeline():
    _stop_event.set()
    return jsonify({"success": True})

@app.route("/api/reset", methods=["POST"])
def api_reset():
    try:
        # 1. Truncate PostgreSQL warehouse tables (only if Postgres is reachable)
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("TRUNCATE TABLE fact_orders, dim_customer, dim_product, dim_date CASCADE;")
            conn.commit()
            conn.close()
        except:
            pass  # Postgres might not be running yet, that's OK

        # 2. Delete all objects inside S3 buckets (only if LocalStack is reachable)
        try:
            s3 = get_s3()
            for bucket in [RAW_BUCKET, CURATED_BUCKET]:
                try:
                    paginator = s3.get_paginator('list_objects_v2')
                    for page in paginator.paginate(Bucket=bucket):
                        if "Contents" in page:
                            delete_keys = [{"Key": obj["Key"]} for obj in page["Contents"]]
                            s3.delete_objects(Bucket=bucket, Delete={"Objects": delete_keys})
                except:
                    pass
        except:
            pass

        # 3. Reset pipeline state
        global pipeline_state
        with _pipeline_lock:
            pipeline_state.update({
                "status":       "idle",
                "current_step": None,
                "steps":        {k: _fresh_step() for k in STEP_KEYS},
                "log":          [],
                "target_date":  "2026-07-01",
                "started_at":   None,
                "ended_at":     None,
                "error":        None,
            })
        return jsonify({"success": True, "message": "Reset completed."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/pipeline_status")
def api_pipeline_status():
    with _pipeline_lock:
        return jsonify({"success": True, "data": {
            **pipeline_state,
            "steps": {k: dict(v) for k, v in pipeline_state["steps"].items()},
            "log":   pipeline_state["log"][-150:],
        }})


# ── Analytics API ──────────────────────────────────────────────────────────────
@app.route("/api/kpis")
def kpis():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""SELECT COUNT(*) AS total_orders, SUM(line_total) AS total_revenue,
            AVG(order_total_amount) AS avg_order_value,
            COUNT(DISTINCT customer_id) AS unique_customers,
            COUNT(DISTINCT sku) AS unique_products, SUM(quantity) AS units_sold
            FROM fact_orders""")
        row  = cur.fetchone()
        cols = [d.name for d in cur.description]
        result = {k: (float(v) if v is not None else 0) for k, v in zip(cols, row)}
        conn.close()
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": True, "data": {"total_orders":0,"total_revenue":0,"avg_order_value":0,"unique_customers":0,"unique_products":0,"units_sold":0}})

@app.route("/api/revenue_by_channel")
def revenue_by_channel():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT channel, SUM(line_total) AS revenue, COUNT(*) AS orders FROM fact_orders GROUP BY channel ORDER BY revenue DESC")
        rows = rows_as_dicts(cur); conn.close()
        for r in rows: r["revenue"] = float(r["revenue"])
        return jsonify({"success": True, "data": rows})
    except:
        return jsonify({"success": True, "data": []})

@app.route("/api/top_skus")
def top_skus():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT sku, SUM(quantity) AS units_sold, SUM(line_total) AS revenue FROM fact_orders GROUP BY sku ORDER BY revenue DESC LIMIT 10")
        rows = rows_as_dicts(cur); conn.close()
        for r in rows: r["units_sold"] = int(r["units_sold"]); r["revenue"] = float(r["revenue"])
        return jsonify({"success": True, "data": rows})
    except:
        return jsonify({"success": True, "data": []})

@app.route("/api/orders")
def orders():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""SELECT order_id, customer_id, sku, channel, order_date::text, quantity,
            unit_price::float, line_total::float, order_total_amount::float, order_item_count
            FROM fact_orders ORDER BY order_date DESC, order_id""")
        rows = rows_as_dicts(cur); conn.close()
        return jsonify({"success": True, "data": rows})
    except:
        return jsonify({"success": True, "data": []})

@app.route("/api/customers")
def customers():
    try:
        conn = get_conn(); cur = conn.cursor()
        # dim_customer schema: customer_id, customer_name, segment (no customer_email column)
        cur.execute("""SELECT c.customer_id, c.customer_name, c.segment,
            COUNT(f.order_id) AS total_orders, SUM(f.line_total)::float AS lifetime_value
            FROM dim_customer c LEFT JOIN fact_orders f ON c.customer_id = f.customer_id
            GROUP BY c.customer_id, c.customer_name, c.segment ORDER BY lifetime_value DESC NULLS LAST LIMIT 20""")
        rows = rows_as_dicts(cur); conn.close()
        for r in rows:
            if r["total_orders"]: r["total_orders"] = int(r["total_orders"])
            if r["lifetime_value"]: r["lifetime_value"] = float(r["lifetime_value"])
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": True, "data": [], "error": str(e)})

@app.route("/api/quarantine")
def quarantine():
    """Read quarantined records from S3 and return them as structured rows."""
    try:
        import json as _json
        s3 = get_s3()
        records = []
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=RAW_BUCKET, Prefix="quarantine/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".jsonl"):
                    continue
                body = s3.get_object(Bucket=RAW_BUCKET, Key=key)["Body"].read().decode("utf-8")
                for line in body.strip().splitlines():
                    if not line.strip():
                        continue
                    try:
                        entry = _json.loads(line)
                        raw = entry.get("raw_record", {})
                        errors = entry.get("errors", [])
                        first_err = errors[0] if errors else {}
                        field = ".".join(str(x) for x in first_err.get("loc", ["unknown"]))
                        reason = first_err.get("msg", entry.get("error_message", "Validation error"))
                        records.append({
                            "order_id":   raw.get("order_id", "—"),
                            "channel":    raw.get("channel", "—"),
                            "bad_field":  field,
                            "reason":     reason,
                            "raw_value":  str(raw.get(field, "—")) if field != "unknown" else "—",
                            "source_key": key.split("/")[-1],
                        })
                    except Exception:
                        pass
        return jsonify({"success": True, "data": records})
    except Exception as e:
        return jsonify({"success": True, "data": [], "error": str(e)})

@app.route("/api/s3_status")
def s3_status():
    try:
        s3 = get_s3(); result = {"raw": [], "curated": [], "quarantine": []}
        for resp in s3.get_paginator("list_objects_v2").paginate(Bucket=RAW_BUCKET, Prefix="raw/"):
            for obj in resp.get("Contents", []): result["raw"].append({"key": obj["Key"], "size": obj["Size"]})
        for resp in s3.get_paginator("list_objects_v2").paginate(Bucket=RAW_BUCKET, Prefix="quarantine/"):
            for obj in resp.get("Contents", []): result["quarantine"].append({"key": obj["Key"], "size": obj["Size"]})
        for resp in s3.get_paginator("list_objects_v2").paginate(Bucket=CURATED_BUCKET, Prefix="curated/"):
            for obj in resp.get("Contents", []): result["curated"].append({"key": obj["Key"], "size": obj["Size"]})
        return jsonify({"success": True, "data": result})
    except:
        return jsonify({"success": True, "data": {"raw":[],"curated":[],"quarantine":[]}})

@app.route("/api/pipeline_health")
def pipeline_health():
    health = {"postgres": False, "localstack_s3": False, "raw_bucket": False, "curated_bucket": False, "fact_orders_count": 0}
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM fact_orders"); health["fact_orders_count"] = cur.fetchone()[0]
        conn.close(); health["postgres"] = True
    except: pass
    try:
        s3 = get_s3(); s3.head_bucket(Bucket=RAW_BUCKET)
        health["localstack_s3"] = True; health["raw_bucket"] = True
    except: pass
    try:
        s3 = get_s3(); s3.head_bucket(Bucket=CURATED_BUCKET); health["curated_bucket"] = True
    except: pass
    return jsonify({"success": True, "data": health})


@app.route("/api/upload_data", methods=["POST"])
def api_upload_data():
    """
    Accept a user-uploaded CSV or JSON file and save it into data/sample_orders/,
    replacing the existing sample file of the same type.
    Accepted: .csv  → replaces pos_export_<date>.csv
              .json → replaces ecommerce_export_<date>.json
    """
    ALLOWED_EXTENSIONS = {".csv", ".json"}

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part in request"}), 400

    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    filename = secure_filename(f.filename)
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"success": False, "error": f"Only .csv and .json files are accepted, got '{ext}'"}), 400

    # Validate size (max 10 MB)
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    if size > 10 * 1024 * 1024:
        return jsonify({"success": False, "error": "File too large (max 10 MB)"}), 400

    sample_dir = os.path.join(PROJECT_ROOT, "data", "sample_orders")
    os.makedirs(sample_dir, exist_ok=True)

    # Determine canonical target filename from extension
    target_date = request.form.get("target_date", "2026-07-01")
    # Sanitise date: allow only YYYY-MM-DD
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target_date):
        target_date = "2026-07-01"

    if ext == ".csv":
        dest_filename = f"pos_export_{target_date}.csv"
    else:
        dest_filename = f"ecommerce_export_{target_date}.json"

    dest_path = os.path.join(sample_dir, dest_filename)
    f.save(dest_path)

    return jsonify({
        "success": True,
        "message": f"Uploaded as '{dest_filename}' — click Start Pipeline to process it.",
        "filename": dest_filename,
        "size": size,
        "type": "csv" if ext == ".csv" else "json",
    })


@app.route("/api/list_data_files")
def api_list_data_files():
    """Return the CSV and JSON files currently in data/sample_orders/."""
    sample_dir = os.path.join(PROJECT_ROOT, "data", "sample_orders")
    files = []
    if os.path.isdir(sample_dir):
        for fname in sorted(os.listdir(sample_dir)):
            ext = os.path.splitext(fname)[1].lower()
            if ext in (".csv", ".json"):
                fpath = os.path.join(sample_dir, fname)
                files.append({
                    "filename": fname,
                    "size": os.path.getsize(fpath),
                    "type": ext.lstrip("."),
                    "modified": datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M"),
                })
    return jsonify({"success": True, "data": files})


if __name__ == "__main__":
    print("RetailFlow Dashboard v3 - Full Infrastructure + Pipeline Control")
    print("Open your browser: http://localhost:5050")
    app.run(host="0.0.0.0", port=5050, debug=False)
