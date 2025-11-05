# Preschool Staffing Ratio Calculator

**Quick Summary:** Web application for calculating preschool staffing requirements based on CA Child Development Permit Matrix and configurable age group ratios.

**Tags:** #preschool #staffing #childcare #california #compliance

## Features

- **Age Group Management**: Configure age ranges and required staff-to-child ratios
- **Staff Management**: Track staff by CA Child Development Permit level
- **Ratio Calculator**: Calculate staffing needs based on current enrollment
- **Supervision Rules**: Implements permit hierarchy from CA regulations
- **Availability Tracking**: Mark staff as available/unavailable for scheduling

## CA Child Development Permit Levels

The application supports all six permit levels from the California Child Development Permit Matrix:

1. **Program Director** - Can supervise all staff, single or multiple sites
2. **Site Supervisor** - Supervises single site operations
3. **Master Teacher** - Coordinates curriculum and staff development
4. **Teacher** - Provides instruction, supervises Associate Teachers and Assistants
5. **Associate Teacher** - Provides instruction, supervises Assistants
6. **Assistant** - Must work under supervision of Associate Teacher or above

## Quick Start

### Using Docker (Recommended)

1. **Start the application:**
   ```bash
   cd /home/rob/AI_assistant/HTHPreschool/staffing-calculator
   docker compose up -d
   ```

2. **Access the application:**
   Open your browser to [http://localhost:5000](http://localhost:5000)

3. **Initialize with sample data:**
   Click the "load sample data" link on the home page, or visit:
   [http://localhost:5000/initialize-db](http://localhost:5000/initialize-db)

4. **Stop the application:**
   ```bash
   docker compose down
   ```

5. **Rebuild after code changes:**
   ```bash
   docker compose down
   docker compose up -d --build
   ```

6. **Restart the application:**
   ```bash
   docker compose restart
   ```

7. **View logs:**
   ```bash
   docker compose logs -f
   ```

8. **Reset database (inside container):**
   ```bash
   docker compose exec web rm -f /app/instance/staffing.db
   docker compose restart
   ```

### Without Docker

1. **Install dependencies:**
   ```bash
   cd /home/rob/AI_assistant/HTHPreschool/staffing-calculator
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   python app.py
   ```

3. **Access the application:**
   Open your browser to [http://localhost:5000](http://localhost:5000)

## Usage Guide

### 1. Configure Age Groups

1. Navigate to **Age Groups** in the menu
2. Click **Add Age Group**
3. Enter:
   - Group name (e.g., "Infants (0-12 months)")
   - Age range in months
   - Required ratio (e.g., "1:4" = 1 staff per 4 children)
4. Click **Save**

**Common California Ratios:**
- Infants (0-12 months): 1:4
- Toddlers (12-24 months): 1:6
- Preschool (2-3 years): 1:8
- Preschool (3-5 years): 1:12

### 2. Add Staff Members

1. Navigate to **Staff** in the menu
2. Click **Add Staff Member**
3. Enter staff name and select their permit level
4. Click **Save**
5. Use the toggle button to mark staff as available/unavailable

### 3. Calculate Staffing Needs

1. Go to **Calculator** (home page)
2. Enter the number of children in each age group
3. Click **Calculate Staffing Needs**
4. Review the results:
   - Staff required per age group
   - Total staff needed
   - Current available staff
   - Adequacy assessment
   - Supervisor availability for Assistants

## Data Persistence

- Database is stored in `instance/staffing.db`
- When using Docker, data persists in the `instance/` directory
- Data survives container restarts and rebuilds

## Project Structure

```
staffing-calculator/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── Dockerfile             # Docker image configuration
├── docker-compose.yml     # Docker Compose configuration
├── templates/             # HTML templates
│   ├── base.html         # Base template
│   ├── index.html        # Calculator page
│   ├── age_groups.html   # Age group management
│   └── staff.html        # Staff management
├── static/               # Static assets
│   └── css/
│       └── style.css     # Custom styles
└── instance/             # Database directory
    └── staffing.db       # SQLite database (created on first run)
```

## Technical Details

- **Backend**: Python Flask
- **Database**: SQLite with Flask-SQLAlchemy
- **Frontend**: Bootstrap 5, vanilla JavaScript
- **Container**: Docker with Python 3.11-slim base image

## Calculation Logic

The application calculates staffing needs using:

1. **Age Group Ratios**: Determines minimum staff per group using ceiling division
2. **Supervision Rules**: Ensures proper supervision hierarchy
3. **Availability Check**: Only counts staff marked as "Available"
4. **Assistant Supervision**: Warns when Assistants cannot be deployed due to lack of supervisors

**Example:**
- Age Group: Preschool (3-5 years), Ratio: 1:12
- Children enrolled: 25
- Staff needed: ⌈25 × 1 / 12⌉ = ⌈2.08⌉ = 3 staff members

## Troubleshooting

**Port already in use:**
```bash
# Change port in docker-compose.yml:
ports:
  - "8080:5000"  # Use port 8080 instead
```

**Reset database:**
```bash
# Stop container
docker compose down

# Remove database (inside container)
docker compose up -d
docker compose exec web rm -f /app/instance/staffing.db
docker compose restart

# Then visit http://localhost:5000/initialize-db to load sample data
```

**View logs:**
```bash
docker compose logs -f
# Or show last 50 lines:
docker compose logs --tail=50
```

**Rebuild after code changes:**
```bash
docker compose down
docker compose up -d --build
```

**Container won't start:**
```bash
# Check logs for errors
docker compose logs

# Try complete cleanup
docker compose down
docker compose up -d --build
```

## Future Enhancements

Possible additions:
- Export reports to PDF/CSV
- Multi-week scheduling
- Staff schedule conflict detection
- Email notifications for understaffing
- Historical data tracking
- Mobile app version

## License

For personal use at HTH Preschool.

---

*Last updated: 2025-11-04*
