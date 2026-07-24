# 🪙 Pennywise — Personal Finance & Analytics Platform

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2+-092E20?style=flat&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.0+-38B2AC?style=flat&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![HTMX](https://img.shields.io/badge/HTMX-1.9+-336699?style=flat)](https://htmx.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-4169E1?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)

> **Pennywise** is a full-stack personal finance application engineered to track transactions, automate recurring income pipelines, manage category budgets, and deliver dynamic BI reporting via real-time analytics dashboards.

![Pennywise Dashboard Preview](assets/Analytics_1.png)
---

## 📌 Features & Highlights
* **🔍 Transaction Filtering:**
  * Server-side pagination (25 items/page), multi-category filtering, date ranges, amount bounds, and dynamic column sorting using **HTMX** for fast SPA-like partial page updates without full reloads.
  ![Pennywise Transactions](assets/Transactions.png)
* **💸 Automated Recurring Income Sync:**
  * Engine that projects historical and upcoming paychecks across configurable frequencies (Weekly, Bi-Weekly, Monthly).
  * Auto-populates missing income records while handling manual skips or custom paycheck overrides.
  ![Pennywise Income](assets/Income.png)
* **📊 Dynamic Analytics & BI Dashboard:**
  * Interactive Chart.js visualizations for category budget allocation, monthly spend vs. income trends, and net savings rate.
  * Real-time progress indicators with status color thresholds (Emerald / Amber / Red) for monthly budget variance tracking.
  ![Pennywise Analytics](assets/Analytics_1.png)
  ![Pennywise Analytics](assets/Analytics_2.png)
* **⚙️ Settings and Configuration:**
  * Configure the spending categories you care about and the allocated monthly budget
  ![Pennywise Settings](assets/Settings.png)


---

## 🛠️ Technical Architecture & Tech Stack

* **Backend Framework:** Python / Django (ORM, Class/Function-Based Views, Authentication)
* **Frontend UI & Interactivity:** Tailwind CSS, HTMX, Chart.js
* **Database:** SQLite (Development/UAT)
* **Data Processing & Analytics:** Django Aggregations (`Sum`, `Coalesce`, `ExtractMonth/Year`), Pandas, Relativedelta

---
## 📈 Key Database Models & Schema Design

| Model | Description | Key Relationships & Constraints |
| :--- | :--- | :--- |
| **`Category`** | User-defined budget buckets with target limits. | `ForeignKey(User)` <br> • *Constraint:* Unique together (`user`, `name`) |
| **`Transaction`** | Individual expense entries mapped to a date and category. | `ForeignKey(User)` <br> • `ForeignKey(Category, SET_NULL)` |
| **`PaycheckTemplate`** | Recurring salary rules (frequency, start date, source) and skipped date tracking. | `ForeignKey(User)` |
| **`PaycheckTransaction`** | Historical and auto-generated income entries. | `ForeignKey(User)` <br> • `ForeignKey(PaycheckTemplate, SET_NULL)` |

---

## 🖥️ Local Development Setup

### 1. Prerequisites
Ensure you have **Python 3.10+** and **Git** installed on your machine.

### 2. Clone the Repository & Set Up Virtual Environment
```bash
git clone [https://github.com/kevzjhu/pennywise.git](https://github.com/kevzjhu/pennywise.git)
cd pennywise

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run Migrations & Seed Admin User
```bash
python manage.py makemigrations
python manage.py migrate

# Create superuser for Django Admin access
python manage.py createsuperuser
```

### 5. Start Development Server
```bash
python manage.py runserver
```

---
## 📝 To Do List:
- Transactions: Add import functionality for CC transactions (CSVs)
- Transactions: Add recurring payments (subscriptions/rent/utilities etc.) much like recurring income rules
- Analytics: create a sankey
- Analytics: ML?
- Deploy and UAT with friends
- Make it work on my phone

---
## 📄 License & Author

Developed by Kevin Hu  
*Health Informatics & Data Analytics Professional*

📧 [Email Me](mailto:kevzjhu@gmail.com) | 💼 [LinkedIn](https://www.linkedin.com/in/kevinhu77/)