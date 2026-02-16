# RegInfo Monitor

Command-line tool to monitor RINs via RegInfo.gov XML exports.

## Install

1. Ensure Python 3.7+ installed, or install Python 3.7+
2. Install dependencies:

```bash
pip install -r requirements.txt
```

### Configure

Edit `config.json`:

```json
{
  "rins": ["####-XX##", "####-XX##, ####-XX##"],
  "keep_files": 2,
  "email": {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "your_email@gmail.com",
    "password": "your_app_password",
    "from_address": "your_email@gmail.com",
    "to_address": "recipient@example.com"
  }
}
```

### Run

```bash
python rin_monitor_cli.py
```
