# Smart Canteen Food Waste Reduction System

A beginner-friendly college project. A Flask + SQLite web app that helps a canteen cut food waste by collecting meal preferences, estimating demand, tracking leftovers, advertising surplus food and reporting waste.

## Features

- **Dashboard**: preference count, food prepared, served and leftover, surplus notices, a 7-day chart.
- **Meal preferences**: students submit name, meal and date (validated, stored in SQLite).
- **Demand estimation**: counts preferences per meal and date, applies a buffer you set.
  `recommended = expected demand x (1 + buffer / 100)`, rounded **up**. Always shown as an *estimate*.
- **Preparation and leftover tracking**: leftover = prepared - served. Negative numbers and served > prepared are rejected.
- **Surplus food**: staff publish a notice (item, quantity, location, deadline) and mark it collected. Expired notices disappear from the active list.
- **Reports**: daily and weekly totals, leftover percentage, bar charts. Works with no data.
- **Roles**: Student, Canteen Staff, Admin, enforced on the server (see the table below).

| Page | Student | Staff | Admin |
|---|---|---|---|
| Dashboard, Preferences, view Surplus | yes | yes | yes |
| Demand, Tracking, Reports, Menu, publish/collect Surplus | no | yes | yes |
| Users and roles | no | no | yes |

## 1. Prerequisites

- Windows 10 or 11
- **Python 3.11** from https://www.python.org/downloads/ (tick **"Add python.exe to PATH"** during install)
- **VS Code** from https://code.visualstudio.com/ (optional but recommended)

Check Python in PowerShell: `py -3.11 --version` (or `python --version`).

## 2. Extract and open the project

1. Right-click `Smart_Canteen_Food_Waste_Reduction_System.zip` and choose **Extract All...**
2. Open VS Code, then **File > Open Folder...** and pick the extracted `Smart_Canteen_Food_Waste_Reduction_System` folder.
3. Open a terminal: **Terminal > New Terminal** (PowerShell).

## 3. Create a virtual environment and install dependencies

```powershell
py -3.11 -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks the activate script, run this once, then activate again:
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
(Or use Command Prompt and run `venv\Scripts\activate.bat`.)

## 4. Set up the database

The database (`instance/canteen.db`) is created automatically the first time the app starts, and existing records are kept on every restart. You can also create it yourself:

```powershell
python init_db.py
```

**Option A, demo data and demo accounts (easiest for a demonstration):**

```powershell
python seed.py
```

This adds sample preferences, two weeks of tracking records and one surplus notice. Running it again changes nothing. It also creates **demo-only** accounts: `admin`, `staff`, `student`, all with the password `Demo@12345`. Do not use these on a real deployment. To pick your own demo password, run `$env:DEMO_PASSWORD="YourPassword1"` before `python seed.py`.

**Option B, real accounts without demo data:** create the first admin (you will be asked for a password in a hidden prompt):

```powershell
python create_user.py myadmin "My Name" admin
```

Students can register themselves on the **Create an account** page (always as Student). Admins can change roles on the **Users** page.

## 5. Start the application

```powershell
python app.py
```

Open **http://127.0.0.1:5000** in your browser. Press `Ctrl+C` in the terminal to stop it.

## 6. Run the automated tests

```powershell
python -m pytest
```

The tests use a temporary database and Flask's built-in test client, so no browser is needed and your real data is never touched.

## 7. Azure DevOps (basic CI)

1. Push the project to a Git repo on your **main** branch (Azure Repos or GitHub). The `.gitignore` already excludes the virtual environment and database.
2. In Azure DevOps open **Pipelines > Create Pipeline**, choose where your code lives, and select **Existing Azure Pipelines YAML file**.
3. Pick branch `main` and path `/azure-pipelines.yml`, then **Run**.
4. The pipeline triggers on pushes to `main`, uses an Ubuntu agent, selects Python 3.11, installs `requirements.txt`, runs `pytest` and publishes the results.

> This pipeline file has **not** been run in Azure DevOps by the author of this package. Check the first run yourself and fix any organisation-specific settings (for example, agent pool permissions).

## Project layout

```
app.py              Flask routes and app factory
database.py         Schema and SQLite helpers
services.py         Validation, demand formula, report queries
init_db.py          Create the database
seed.py             Optional demo data (idempotent)
create_user.py      Create a real account from the command line
templates/          HTML pages (Jinja2)
static/             CSS and a small menu script
tests/              Pytest tests
azure-pipelines.yml CI pipeline
```

## Notes and limitations

- Demand estimates only count submitted preferences, not walk-ins or no-shows.
- Built for demonstration: Flask's development server, SQLite, no email, no password reset. For real use, put it behind a production server (for example waitress) with HTTPS and set a `SECRET_KEY` environment variable.
- The first run creates `instance/secret_key.txt` (random, git-ignored) to sign login sessions.
- A starter menu of five meals is added once to an empty database. Staff can edit it on the **Menu** page.
- Charts are plain HTML/CSS bars, so they work offline.
