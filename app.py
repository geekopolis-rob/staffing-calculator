from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///staffing.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Plan structure constants
SCHEDULE_TYPES = {
    'core': {'name': 'Core Hours', 'start': '9:00 AM', 'end': '3:00 PM'},
    'extended': {'name': 'Extended Hours', 'start': '7:30 AM', 'end': '5:30 PM'}
}

DAY_PATTERNS = {
    'full': {'name': 'Mon-Fri', 'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'], 'count': 5},
    'mwf': {'name': 'Mon/Wed/Fri', 'days': ['monday', 'wednesday', 'friday'], 'count': 3},
    'tth': {'name': 'Tue/Thu', 'days': ['tuesday', 'thursday'], 'count': 2}
}

AGE_GROUP_TYPES = {
    'infant': {'name': 'Infant', 'description': '4 months - 2 years'},
    'child': {'name': 'Child', 'description': '2+ years'}
}

EXPENSE_CATEGORIES = {
    'utility': 'Utilities',
    'lease': 'Lease/Rent',
    'professional': 'Professional Services',
    'contract': 'Class Contracts'
}

# Template filters
@app.template_filter('format_time')
def format_time_filter(time_str):
    """Convert time to 12-hour format like '9:00 AM'"""
    if not time_str:
        return ''
    try:
        # Try parsing with AM/PM first
        if 'AM' in time_str or 'PM' in time_str:
            dt = datetime.strptime(time_str.strip(), '%I:%M %p')
        else:
            dt = datetime.strptime(time_str.strip(), '%H:%M')
        # Format as "9:00 AM" (no leading zero for hour)
        return dt.strftime('%-I:%M %p').lstrip('0') if '%-I' in dt.strftime('%-I:%M %p') else dt.strftime('%I:%M %p').lstrip('0')
    except:
        return time_str

# Database Models
class AgeGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    min_age_months = db.Column(db.Integer, nullable=False)
    max_age_months = db.Column(db.Integer, nullable=False)
    required_ratio = db.Column(db.String(10), nullable=False)  # e.g., "1:4" (basic ratio)
    enhanced_ratios = db.Column(db.Text, nullable=True)  # JSON array of enhanced ratio objects
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_ratio_parts(self):
        """Returns (staff, children) tuple from ratio string"""
        parts = self.required_ratio.split(':')
        return int(parts[0]), int(parts[1])

    def get_enhanced_ratios(self):
        """Returns list of enhanced ratio options"""
        if not self.enhanced_ratios:
            return []
        import json
        try:
            return json.loads(self.enhanced_ratios)
        except:
            return []

class StaffMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    permit_level = db.Column(db.String(50), nullable=False)
    is_available = db.Column(db.Boolean, default=True)
    hourly_rate = db.Column(db.Float, default=0.0)  # Hourly pay rate
    ece_units = db.Column(db.Integer, default=0)  # ECE/CD units completed (for aide qualifications)
    has_infant_specialization = db.Column(db.Boolean, default=False)  # 3+ units in infant care
    is_fully_qualified = db.Column(db.Boolean, default=True)  # Has 12 units + 6 months experience
    is_director = db.Column(db.Boolean, default=False)  # Track if this is the facility director
    director_counts_toward_ratio = db.Column(db.Boolean, default=False)  # Director teaching vs admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CorePlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    base_price = db.Column(db.Float, nullable=False)
    billing_period = db.Column(db.String(20), nullable=False)  # 'weekly' or 'monthly'
    age_group_id = db.Column(db.Integer, db.ForeignKey('age_group.id'), nullable=True)  # Optional age group link

    # Fixed plan structure fields
    schedule_type = db.Column(db.String(20), nullable=True)  # 'core' or 'extended'
    day_pattern = db.Column(db.String(20), nullable=True)    # 'full', 'mwf', or 'tth'
    age_group_type = db.Column(db.String(20), nullable=True) # 'infant' or 'child'
    is_fixed_plan = db.Column(db.Boolean, default=False)

    # Day fields (auto-populated for fixed plans)
    monday = db.Column(db.Boolean, default=True)
    tuesday = db.Column(db.Boolean, default=True)
    wednesday = db.Column(db.Boolean, default=True)
    thursday = db.Column(db.Boolean, default=True)
    friday = db.Column(db.Boolean, default=True)
    start_time = db.Column(db.String(10), default='9:00 AM')
    end_time = db.Column(db.String(10), default='3:00 PM')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_days_selected(self):
        """Returns list of selected day names"""
        if self.day_pattern and self.day_pattern in DAY_PATTERNS:
            return [d[:3].title() for d in DAY_PATTERNS[self.day_pattern]['days']]
        days = []
        if self.monday: days.append('Mon')
        if self.tuesday: days.append('Tue')
        if self.wednesday: days.append('Wed')
        if self.thursday: days.append('Thu')
        if self.friday: days.append('Fri')
        return days

    def get_days_count(self):
        """Returns number of days selected"""
        if self.day_pattern and self.day_pattern in DAY_PATTERNS:
            return DAY_PATTERNS[self.day_pattern]['count']
        return len(self.get_days_selected())

    def get_schedule_display(self):
        """Returns formatted schedule like 'Mon, Wed, Fri 9:00 AM - 3:00 PM'"""
        days_str = ', '.join(self.get_days_selected())
        if self.schedule_type and self.schedule_type in SCHEDULE_TYPES:
            schedule = SCHEDULE_TYPES[self.schedule_type]
            return f"{days_str} {schedule['start']} - {schedule['end']}"
        return f"{days_str} {self.start_time} - {self.end_time}"

    def get_age_group_display(self):
        """Returns age group label for fixed plans"""
        if self.age_group_type and self.age_group_type in AGE_GROUP_TYPES:
            return AGE_GROUP_TYPES[self.age_group_type]['name']
        return 'All Ages'

class AddOn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    pricing_type = db.Column(db.String(20), nullable=False)  # 'per_day', 'time_based', 'one_time', 'extended_care'
    price = db.Column(db.Float, nullable=False)  # Base price or rate per minute
    minutes_unit = db.Column(db.Integer, default=1)  # For time_based: price per X minutes (e.g., $5 per 15 min)
    is_extended_care = db.Column(db.Boolean, default=False)  # Flag for extended care add-ons
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OneTimeFee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    amount = db.Column(db.Float, nullable=False)
    fee_type = db.Column(db.String(50), nullable=False)  # 'registration', 'materials', 'deposit', 'other'
    is_active = db.Column(db.Boolean, default=True)
    is_refundable = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Discount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    discount_type = db.Column(db.String(20), nullable=False)  # 'percentage' or 'fixed'
    amount = db.Column(db.Float, nullable=False)  # Percentage (e.g., 10 for 10%) or fixed dollar amount
    applies_to = db.Column(db.String(50), nullable=False)  # 'core_plan', 'add_ons', 'total', 'fees'
    conditions = db.Column(db.Text)  # Description of when this applies (e.g., "2nd child", "annual payment")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EnrollmentPackage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    short_code = db.Column(db.String(10), nullable=True)  # Short code for calendar display
    description = db.Column(db.Text)
    age_group_id = db.Column(db.Integer, db.ForeignKey('age_group.id'), nullable=True)
    core_plan_id = db.Column(db.Integer, db.ForeignKey('core_plan.id'), nullable=False)
    extended_care_start_time = db.Column(db.String(10), nullable=True)  # e.g., "7:00 AM"
    extended_care_end_time = db.Column(db.String(10), nullable=True)  # e.g., "6:00 PM"
    monthly_tuition = db.Column(db.Float, nullable=False)  # Calculated total monthly cost
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    core_plan = db.relationship('CorePlan', backref='packages')
    age_group = db.relationship('AgeGroup', backref='packages')

class PackageAddOn(db.Model):
    """Junction table for packages and add-ons with quantity"""
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey('enrollment_package.id'), nullable=False)
    addon_id = db.Column(db.Integer, db.ForeignKey('add_on.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)  # days per week or minutes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    package = db.relationship('EnrollmentPackage', backref='package_addons')
    addon = db.relationship('AddOn', backref='package_addons')

class PackageFee(db.Model):
    """Junction table for packages and one-time fees"""
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey('enrollment_package.id'), nullable=False)
    fee_id = db.Column(db.Integer, db.ForeignKey('one_time_fee.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    package = db.relationship('EnrollmentPackage', backref='package_fees')
    fee = db.relationship('OneTimeFee', backref='package_fees')

class PackageDiscount(db.Model):
    """Junction table for packages and discounts"""
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey('enrollment_package.id'), nullable=False)
    discount_id = db.Column(db.Integer, db.ForeignKey('discount.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    package = db.relationship('EnrollmentPackage', backref='package_discounts')
    discount = db.relationship('Discount', backref='package_discounts')

class Enrollment(db.Model):
    """Bulk enrollment tracking - number of children in a package (DEPRECATED - use CapacitySettings)"""
    id = db.Column(db.Integer, primary_key=True)
    enrollment_package_id = db.Column(db.Integer, db.ForeignKey('enrollment_package.id'), nullable=False)
    age_group_id = db.Column(db.Integer, db.ForeignKey('age_group.id'), nullable=False)
    child_count = db.Column(db.Integer, nullable=False, default=1)  # Number of children
    status = db.Column(db.String(20), default='active')  # 'active' or 'inactive'
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    age_group = db.relationship('AgeGroup', backref='enrollments')
    package = db.relationship('EnrollmentPackage', backref='enrollments')


class CapacitySettings(db.Model):
    """
    Capacity planner settings - source of truth for enrollment distribution.
    Stores the ratios that determine how children are distributed across plans.
    """
    id = db.Column(db.Integer, primary_key=True)
    total_children = db.Column(db.Integer, nullable=False, default=50)
    max_capacity = db.Column(db.Integer, nullable=False, default=100)  # Licensed capacity

    # Age mix percentages (must total 100)
    infant_percent = db.Column(db.Float, nullable=False, default=20.0)
    child_percent = db.Column(db.Float, nullable=False, default=80.0)

    # Schedule mix percentages (must total 100)
    core_percent = db.Column(db.Float, nullable=False, default=50.0)
    extended_percent = db.Column(db.Float, nullable=False, default=50.0)

    # Days mix percentages (must total 100)
    full_percent = db.Column(db.Float, nullable=False, default=60.0)  # Mon-Fri
    mwf_percent = db.Column(db.Float, nullable=False, default=30.0)   # Mon/Wed/Fri
    tth_percent = db.Column(db.Float, nullable=False, default=10.0)   # Tue/Thu

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_age_mix(self):
        return {'infant': self.infant_percent, 'child': self.child_percent}

    def get_schedule_mix(self):
        return {'core': self.core_percent, 'extended': self.extended_percent}

    def get_days_mix(self):
        return {'full': self.full_percent, 'mwf': self.mwf_percent, 'tth': self.tth_percent}

    @staticmethod
    def get_or_create():
        """Get the singleton settings record, creating with defaults if needed"""
        settings = CapacitySettings.query.first()
        if not settings:
            settings = CapacitySettings()
            db.session.add(settings)
            db.session.commit()
        return settings


class FixedExpense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    monthly_amount = db.Column(db.Float, nullable=False, default=0.0)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PerChildCost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    age_group_type = db.Column(db.String(20), nullable=False)  # 'infant' or 'child'
    schedule_type = db.Column(db.String(20), nullable=False)   # 'core' or 'extended'
    monthly_rate = db.Column(db.Float, nullable=False, default=0.0)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Permit levels and their supervision capabilities
PERMIT_LEVELS = {
    'Program Director': {
        'rank': 6,
        'can_supervise': ['Site Supervisor', 'Master Teacher', 'Teacher', 'Associate Teacher', 'Assistant'],
        'can_teach': True,
        'max_assistants': 4,  # Can supervise up to 4 assistants simultaneously
        'needs_supervision': False
    },
    'Site Supervisor': {
        'rank': 5,
        'can_supervise': ['Master Teacher', 'Teacher', 'Associate Teacher', 'Assistant'],
        'can_teach': True,
        'max_assistants': 4,  # Can supervise up to 4 assistants simultaneously
        'needs_supervision': False
    },
    'Master Teacher': {
        'rank': 4,
        'can_supervise': ['Teacher', 'Associate Teacher', 'Assistant'],
        'can_teach': True,
        'max_assistants': 3,  # Can supervise up to 3 assistants simultaneously
        'needs_supervision': False
    },
    'Teacher': {
        'rank': 3,
        'can_supervise': ['Associate Teacher', 'Assistant'],
        'can_teach': True,
        'max_assistants': 2,  # Can supervise up to 2 assistants simultaneously
        'needs_supervision': False
    },
    'Associate Teacher': {
        'rank': 2,
        'can_supervise': ['Assistant'],
        'can_teach': True,
        'max_assistants': 1,  # Can supervise 1 assistant
        'needs_supervision': False
    },
    'Assistant': {
        'rank': 1,
        'can_supervise': [],
        'can_teach': False,  # Must work under supervision
        'max_assistants': 0,
        'needs_supervision': True
    }
}

def calculate_supervisor_capacity(available_staff):
    """
    Calculate how many assistants can be supervised based on available supervisors.
    Returns: (max_assistants, breakdown_by_level)
    """
    capacity = 0
    breakdown = {}

    for staff in available_staff:
        if staff.permit_level == 'Assistant':
            continue

        max_assistants = PERMIT_LEVELS.get(staff.permit_level, {}).get('max_assistants', 0)
        capacity += max_assistants

        if staff.permit_level not in breakdown:
            breakdown[staff.permit_level] = {'count': 0, 'capacity': 0}
        breakdown[staff.permit_level]['count'] += 1
        breakdown[staff.permit_level]['capacity'] += max_assistants

    return capacity, breakdown

def check_infant_qualifications(staff_member):
    """
    Check if staff member meets infant care teacher requirements.
    Returns: (qualified, reasons)
    """
    reasons = []

    if not staff_member.is_fully_qualified:
        reasons.append("Not fully qualified (needs 12 ECE units + 6 months experience)")

    if not staff_member.has_infant_specialization:
        reasons.append("Missing 3+ units in infant care specialization")

    qualified = len(reasons) == 0
    return qualified, reasons

def suggest_staff_assignments(age_group_data, available_staff):
    """
    Suggest which staff should be assigned to which age groups based on qualifications.
    Returns: dict with assignments and warnings
    """
    assignments = []
    warnings = []

    # Filter staff by director status
    teaching_staff = [s for s in available_staff
                     if not s.is_director or s.director_counts_toward_ratio]

    for data in age_group_data:
        age_group = AgeGroup.query.get(data['age_group_id'])
        child_count = data['child_count']

        if child_count == 0 or not age_group:
            continue

        assignment = {
            'age_group': age_group.name,
            'children': child_count,
            'suggested_staff': [],
            'warnings': []
        }

        # Check if this is an infant group
        is_infant = age_group.min_age_months < 18

        if is_infant:
            # Find qualified infant teachers
            qualified_infant_staff = [s for s in teaching_staff
                                     if check_infant_qualifications(s)[0]]

            if len(qualified_infant_staff) == 0:
                assignment['warnings'].append(
                    "No staff with infant specialization available. All infant teachers must have 3+ units in infant care."
                )
            else:
                assignment['suggested_staff'] = [
                    {'name': s.name, 'level': s.permit_level, 'reason': 'Infant qualified'}
                    for s in qualified_infant_staff[:4]  # Suggest up to 4
                ]
        else:
            # For non-infant groups, suggest highest-ranked available staff
            qualified_staff = sorted(
                [s for s in teaching_staff if s.is_fully_qualified],
                key=lambda x: PERMIT_LEVELS.get(x.permit_level, {}).get('rank', 0),
                reverse=True
            )

            assignment['suggested_staff'] = [
                {'name': s.name, 'level': s.permit_level, 'reason': 'Qualified teacher'}
                for s in qualified_staff[:4]  # Suggest up to 4
            ]

        assignments.append(assignment)

    return {'assignments': assignments, 'warnings': warnings}

def evaluate_ratio_option(child_count, ratio_str):
    """Helper: Calculate staff needed for a given ratio"""
    parts = ratio_str.split(':')
    staff_ratio, child_ratio = int(parts[0]), int(parts[1])
    return -(-child_count * staff_ratio // child_ratio)  # Ceiling division

def can_use_enhanced_ratio(enhanced_option, available_staff):
    """
    Check if facility has required staff composition for an enhanced ratio.

    enhanced_option: dict with 'ratio', 'requires_teachers', 'requires_aides', 'aide_min_ece_units'
    available_staff: list of StaffMember objects
    Returns: (bool, str) - (can_use, reason)
    """
    requires_teachers = enhanced_option.get('requires_teachers', 1)
    requires_aides = enhanced_option.get('requires_aides', 0)
    aide_min_ece = enhanced_option.get('aide_min_ece_units', 0)

    # Count qualified teachers (Associate Teacher or above)
    qualified_teachers = [s for s in available_staff
                         if PERMIT_LEVELS.get(s.permit_level, {}).get('rank', 0) >= 2]

    # Count qualified aides (Assistants with required ECE units)
    qualified_aides = [s for s in available_staff
                      if s.permit_level == 'Assistant' and s.ece_units >= aide_min_ece]

    if len(qualified_teachers) < requires_teachers:
        return False, f"Need {requires_teachers} qualified teacher(s), have {len(qualified_teachers)}"

    if len(qualified_aides) < requires_aides:
        return False, f"Need {requires_aides} aide(s) with {aide_min_ece}+ ECE units, have {len(qualified_aides)}"

    return True, "Requirements met"

def calculate_staffing_needs(age_group_data):
    """
    Calculate staffing requirements based on children counts and ratios.
    Evaluates basic and enhanced ratio options.
    Includes qualification checks and assignment suggestions.

    age_group_data: list of dicts with 'age_group_id' and 'child_count'
    Returns: dict with staffing analysis
    """
    results = {
        'age_groups': [],
        'total_staff_needed': 0,
        'minimum_teachers_needed': 0,
        'can_use_assistants': False,
        'supervisor_capacity': {},
        'qualification_warnings': [],
        'director_info': {}
    }

    total_staff_needed = 0
    available_staff = StaffMember.query.filter_by(is_available=True).all()

    # Calculate supervisor capacity for assistants
    max_assistants, supervisor_breakdown = calculate_supervisor_capacity(available_staff)
    results['supervisor_capacity'] = {
        'max_assistants': max_assistants,
        'breakdown': supervisor_breakdown
    }

    # Check for director and their status
    directors = [s for s in available_staff if s.is_director]
    if directors:
        director = directors[0]  # Assume one director per facility
        results['director_info'] = {
            'name': director.name,
            'level': director.permit_level,
            'counts_toward_ratio': director.director_counts_toward_ratio,
            'status': 'Teaching' if director.director_counts_toward_ratio else 'Administrative only'
        }
        if not director.director_counts_toward_ratio:
            results['qualification_warnings'].append(
                f"Director {director.name} is not counted toward staffing ratios (administrative duties only)"
            )

    for data in age_group_data:
        age_group = AgeGroup.query.get(data['age_group_id'])
        child_count = data['child_count']

        if child_count > 0 and age_group:
            # Calculate basic ratio
            basic_staff_needed = evaluate_ratio_option(child_count, age_group.required_ratio)

            group_result = {
                'name': age_group.name,
                'children': child_count,
                'ratio': age_group.required_ratio,
                'staff_needed': basic_staff_needed,
                'ratio_used': 'basic',
                'enhanced_options': [],
                'qualification_warnings': []
            }

            # Check for infant qualification requirements
            is_infant = age_group.min_age_months < 18
            if is_infant:
                qualified_infant_staff = [s for s in available_staff
                                         if check_infant_qualifications(s)[0]]
                if len(qualified_infant_staff) < basic_staff_needed:
                    group_result['qualification_warnings'].append(
                        f"Need {basic_staff_needed} infant-qualified teachers, only {len(qualified_infant_staff)} available"
                    )

            # Evaluate enhanced ratio options
            enhanced_ratios = age_group.get_enhanced_ratios()
            for enhanced in enhanced_ratios:
                enhanced_staff_needed = evaluate_ratio_option(child_count, enhanced['ratio'])
                can_use, reason = can_use_enhanced_ratio(enhanced, available_staff)

                option_info = {
                    'ratio': enhanced['ratio'],
                    'staff_needed': enhanced_staff_needed,
                    'can_use': can_use,
                    'reason': reason,
                    'description': enhanced.get('description', ''),
                    'requirements': {
                        'teachers': enhanced.get('requires_teachers', 1),
                        'aides': enhanced.get('requires_aides', 0),
                        'aide_min_ece': enhanced.get('aide_min_ece_units', 0)
                    }
                }
                group_result['enhanced_options'].append(option_info)

                # Use best available enhanced ratio if applicable
                if can_use and enhanced_staff_needed < group_result['staff_needed']:
                    group_result['ratio'] = enhanced['ratio']
                    group_result['staff_needed'] = enhanced_staff_needed
                    group_result['ratio_used'] = 'enhanced'
                    group_result['enhanced_description'] = enhanced.get('description', '')

            results['age_groups'].append(group_result)
            total_staff_needed += group_result['staff_needed']

    results['total_staff_needed'] = total_staff_needed
    results['minimum_teachers_needed'] = total_staff_needed

    # Build staff availability info and calculate costs
    staff_by_level = {}
    total_hourly_cost = 0.0
    staff_cost_breakdown = []

    for staff in available_staff:
        level = staff.permit_level
        if level not in staff_by_level:
            staff_by_level[level] = []
        staff_by_level[level].append({
            'id': staff.id,
            'name': staff.name,
            'ece_units': staff.ece_units,
            'hourly_rate': staff.hourly_rate
        })

        # Add to cost calculations
        total_hourly_cost += staff.hourly_rate
        staff_cost_breakdown.append({
            'name': staff.name,
            'level': staff.permit_level,
            'hourly_rate': staff.hourly_rate
        })

    results['available_staff'] = staff_by_level
    results['is_adequately_staffed'] = len(available_staff) >= total_staff_needed

    # Add cost calculations
    results['cost_analysis'] = {
        'total_hourly_cost': round(total_hourly_cost, 2),
        'daily_cost_8hr': round(total_hourly_cost * 8, 2),
        'weekly_cost_40hr': round(total_hourly_cost * 40, 2),
        'monthly_cost_160hr': round(total_hourly_cost * 160, 2),
        'annual_cost': round(total_hourly_cost * 2080, 2),
        'staff_breakdown': staff_cost_breakdown,
        'average_hourly_rate': round(total_hourly_cost / len(available_staff), 2) if available_staff else 0
    }

    # Determine if assistants can be deployed
    # Assistants need supervision from Associate Teacher or above
    teacher_count = sum(len(staff_by_level.get(level, []))
                       for level in PERMIT_LEVELS.keys()
                       if PERMIT_LEVELS[level]['rank'] >= 2)

    results['can_use_assistants'] = teacher_count > 0
    results['available_supervisors'] = teacher_count

    # Generate staff assignment suggestions
    assignment_suggestions = suggest_staff_assignments(age_group_data, available_staff)
    results['suggested_assignments'] = assignment_suggestions

    # Count assistants currently in staff
    assistant_count = len([s for s in available_staff if s.permit_level == 'Assistant'])
    if assistant_count > max_assistants:
        results['qualification_warnings'].append(
            f"Have {assistant_count} assistants but can only supervise {max_assistants} simultaneously"
        )

    return results

def create_fixed_plans():
    """Create the 12 fixed plan combinations"""
    # Prices for each combination (schedule_type, day_pattern, age_group_type)
    base_prices = {
        ('core', 'full', 'infant'): 1800.00,
        ('core', 'full', 'child'): 1550.00,
        ('core', 'mwf', 'infant'): 1400.00,
        ('core', 'mwf', 'child'): 1250.00,
        ('core', 'tth', 'infant'): 1100.00,
        ('core', 'tth', 'child'): 1000.00,
        ('extended', 'full', 'infant'): 2500.00,
        ('extended', 'full', 'child'): 2200.00,
        ('extended', 'mwf', 'infant'): 1950.00,
        ('extended', 'mwf', 'child'): 1800.00,
        ('extended', 'tth', 'infant'): 1400.00,
        ('extended', 'tth', 'child'): 1300.00,
    }

    created_plans = []
    for schedule_type in ['core', 'extended']:
        for day_pattern in ['full', 'mwf', 'tth']:
            for age_group_type in ['infant', 'child']:
                # Check if this combination already exists
                existing = CorePlan.query.filter_by(
                    schedule_type=schedule_type,
                    day_pattern=day_pattern,
                    age_group_type=age_group_type,
                    is_fixed_plan=True
                ).first()

                if not existing:
                    schedule = SCHEDULE_TYPES[schedule_type]
                    pattern = DAY_PATTERNS[day_pattern]
                    age = AGE_GROUP_TYPES[age_group_type]

                    name = f"{age['name']} {pattern['name']} {schedule['name']}"
                    price = base_prices.get((schedule_type, day_pattern, age_group_type), 1000.00)

                    plan = CorePlan(
                        name=name,
                        description=f"{age['name']} program ({age['description']}), {pattern['name']}, {schedule['name']}",
                        base_price=price,
                        billing_period='monthly',
                        schedule_type=schedule_type,
                        day_pattern=day_pattern,
                        age_group_type=age_group_type,
                        monday='monday' in pattern['days'],
                        tuesday='tuesday' in pattern['days'],
                        wednesday='wednesday' in pattern['days'],
                        thursday='thursday' in pattern['days'],
                        friday='friday' in pattern['days'],
                        start_time=schedule['start'],
                        end_time=schedule['end'],
                        is_active=True,
                        is_fixed_plan=True
                    )
                    db.session.add(plan)
                    created_plans.append(name)

    db.session.commit()
    return created_plans

def calculate_capacity_plan(age_mix, schedule_mix, days_mix, total_children):
    """
    Calculate capacity planning simulation based on enrollment ratios.

    Args:
        age_mix: dict with 'infant' and 'child' percentages (must total 100)
        schedule_mix: dict with 'core' and 'extended' percentages (must total 100)
        days_mix: dict with 'full', 'mwf', 'tth' percentages (must total 100)
        total_children: int total number of children to distribute

    Returns:
        dict with enrollment distribution and staff requirements
    """
    import math

    # Convert percentages to decimals
    age_ratios = {k: v / 100 for k, v in age_mix.items()}
    schedule_ratios = {k: v / 100 for k, v in schedule_mix.items()}
    days_ratios = {k: v / 100 for k, v in days_mix.items()}

    # Calculate distribution across all 12 plan combinations
    distribution = []
    running_total = 0
    plan_combinations = []

    for schedule_type in ['core', 'extended']:
        for day_pattern in ['full', 'mwf', 'tth']:
            for age_group_type in ['infant', 'child']:
                plan_combinations.append({
                    'schedule_type': schedule_type,
                    'day_pattern': day_pattern,
                    'age_group_type': age_group_type
                })

    # Calculate raw distribution (may have fractional children)
    raw_distribution = []
    for combo in plan_combinations:
        raw_count = (
            total_children *
            age_ratios.get(combo['age_group_type'], 0) *
            schedule_ratios.get(combo['schedule_type'], 0) *
            days_ratios.get(combo['day_pattern'], 0)
        )
        raw_distribution.append({
            **combo,
            'raw_count': raw_count,
            'count': int(raw_count)  # Floor for now
        })

    # Adjust to match total (distribute remainders)
    current_total = sum(d['count'] for d in raw_distribution)
    remainder = total_children - current_total

    # Sort by fractional part descending to distribute remainders fairly
    sorted_by_fraction = sorted(
        enumerate(raw_distribution),
        key=lambda x: x[1]['raw_count'] - int(x[1]['raw_count']),
        reverse=True
    )

    for i in range(remainder):
        idx = sorted_by_fraction[i % len(sorted_by_fraction)][0]
        raw_distribution[idx]['count'] += 1

    # Build final distribution with display names
    for combo in raw_distribution:
        schedule = SCHEDULE_TYPES[combo['schedule_type']]
        pattern = DAY_PATTERNS[combo['day_pattern']]
        age = AGE_GROUP_TYPES[combo['age_group_type']]

        distribution.append({
            'schedule_type': combo['schedule_type'],
            'schedule_name': schedule['name'],
            'day_pattern': combo['day_pattern'],
            'day_pattern_name': pattern['name'],
            'days_count': pattern['count'],
            'age_group_type': combo['age_group_type'],
            'age_group_name': age['name'],
            'children': combo['count'],
            'plan_name': f"{age['name']} {pattern['name']} {schedule['name']}"
        })

    # Calculate peak day attendance
    # Monday: Full-time + 3-day (MWF) children
    # Tuesday: Full-time + 2-day (TTh) children
    # Wednesday: Full-time + 3-day (MWF) children
    # Thursday: Full-time + 2-day (TTh) children
    # Friday: Full-time + 3-day (MWF) children

    def get_children_by_day_pattern(pattern, age_type=None):
        return sum(
            d['children'] for d in distribution
            if d['day_pattern'] == pattern and
               (age_type is None or d['age_group_type'] == age_type)
        )

    full_infants = get_children_by_day_pattern('full', 'infant')
    mwf_infants = get_children_by_day_pattern('mwf', 'infant')
    tth_infants = get_children_by_day_pattern('tth', 'infant')

    full_children = get_children_by_day_pattern('full', 'child')
    mwf_children = get_children_by_day_pattern('mwf', 'child')
    tth_children = get_children_by_day_pattern('tth', 'child')

    daily_attendance = {
        'Monday': {
            'infants': full_infants + mwf_infants,
            'children': full_children + mwf_children
        },
        'Tuesday': {
            'infants': full_infants + tth_infants,
            'children': full_children + tth_children
        },
        'Wednesday': {
            'infants': full_infants + mwf_infants,
            'children': full_children + mwf_children
        },
        'Thursday': {
            'infants': full_infants + tth_infants,
            'children': full_children + tth_children
        },
        'Friday': {
            'infants': full_infants + mwf_infants,
            'children': full_children + mwf_children
        }
    }

    # Add totals to each day
    for day, counts in daily_attendance.items():
        counts['total'] = counts['infants'] + counts['children']

    # Find peak day
    peak_day = max(daily_attendance.items(), key=lambda x: x[1]['total'])
    peak_day_name = peak_day[0]
    peak_attendance = peak_day[1]

    # Calculate staff requirements based on peak day
    # Infants: 1:4 ratio
    # Children: 1:12 ratio (basic)
    infant_ratio = 4  # 1 teacher per 4 infants
    child_ratio = 12  # 1 teacher per 12 children (basic)

    infant_teachers_needed = math.ceil(peak_attendance['infants'] / infant_ratio) if peak_attendance['infants'] > 0 else 0
    child_teachers_needed = math.ceil(peak_attendance['children'] / child_ratio) if peak_attendance['children'] > 0 else 0

    staff_requirements = {
        'peak_day': peak_day_name,
        'peak_infants': peak_attendance['infants'],
        'peak_children': peak_attendance['children'],
        'peak_total': peak_attendance['total'],
        'infant_staff': {
            'count': infant_teachers_needed,
            'ratio': f"1:{infant_ratio}",
            'note': 'Must have infant specialization (3+ units infant care)'
        },
        'child_staff': {
            'count': child_teachers_needed,
            'ratio': f"1:{child_ratio}",
            'note': 'Basic ratio. Enhanced ratios available with aides.'
        },
        'total_teachers_needed': infant_teachers_needed + child_teachers_needed,
        'enhanced_options': []
    }

    # Calculate enhanced ratio options for children
    if peak_attendance['children'] > 0:
        # 1:15 with 1 teacher + 1 aide
        staff_at_15 = math.ceil(peak_attendance['children'] / 15)
        # 1:18 with 1 teacher + 1 aide (6+ ECE units)
        staff_at_18 = math.ceil(peak_attendance['children'] / 18)

        staff_requirements['enhanced_options'] = [
            {
                'ratio': '1:15',
                'description': '1 teacher + 1 aide per group',
                'teachers_needed': staff_at_15,
                'aides_needed': staff_at_15,
                'total_staff': staff_at_15 * 2
            },
            {
                'ratio': '1:18',
                'description': '1 teacher + 1 aide (6+ ECE units) per group',
                'teachers_needed': staff_at_18,
                'aides_needed': staff_at_18,
                'aide_requirements': '6+ ECE units',
                'total_staff': staff_at_18 * 2
            }
        ]

    # Summary by schedule type (core vs extended)
    schedule_summary = {
        'core': {
            'infants': sum(d['children'] for d in distribution if d['schedule_type'] == 'core' and d['age_group_type'] == 'infant'),
            'children': sum(d['children'] for d in distribution if d['schedule_type'] == 'core' and d['age_group_type'] == 'child')
        },
        'extended': {
            'infants': sum(d['children'] for d in distribution if d['schedule_type'] == 'extended' and d['age_group_type'] == 'infant'),
            'children': sum(d['children'] for d in distribution if d['schedule_type'] == 'extended' and d['age_group_type'] == 'child')
        }
    }

    for sched in schedule_summary.values():
        sched['total'] = sched['infants'] + sched['children']

    # Labor cost calculations
    # Query available staff for rate information
    available_staff = StaffMember.query.filter_by(is_available=True).all()

    # Calculate average rates by role
    teachers = [s for s in available_staff if PERMIT_LEVELS.get(s.permit_level, {}).get('rank', 0) >= 3]
    aides = [s for s in available_staff if PERMIT_LEVELS.get(s.permit_level, {}).get('rank', 0) < 3]

    avg_teacher_rate = sum(s.hourly_rate for s in teachers) / len(teachers) if teachers else 25.00
    avg_aide_rate = sum(s.hourly_rate for s in aides) / len(aides) if aides else 18.00

    # Shift hours with 30-min buffer before and after
    CORE_SHIFT_HOURS = 7.0  # 8:30am-3:30pm (6hr program + 1hr buffer)
    EXTENDED_AM_HOURS = 6.0  # 7:00am-1:00pm
    EXTENDED_PM_HOURS = 5.5  # 12:30pm-6:00pm

    # Calculate staff needed for each schedule type based on distribution
    core_infants = schedule_summary['core']['infants']
    core_children = schedule_summary['core']['children']
    extended_infants = schedule_summary['extended']['infants']
    extended_children = schedule_summary['extended']['children']

    # Staff needed for core (single shift)
    core_infant_staff = math.ceil(core_infants / 4) if core_infants > 0 else 0
    core_child_staff = math.ceil(core_children / 12) if core_children > 0 else 0

    # Staff needed for extended (2 shifts to avoid overtime)
    extended_infant_staff = math.ceil(extended_infants / 4) if extended_infants > 0 else 0
    extended_child_staff = math.ceil(extended_children / 12) if extended_children > 0 else 0

    # Positions needed (extended needs AM + PM coverage)
    core_positions = core_infant_staff + core_child_staff
    extended_positions_per_shift = extended_infant_staff + extended_child_staff
    extended_total_positions = extended_positions_per_shift * 2  # AM + PM shifts

    total_positions = core_positions + extended_total_positions

    # Daily labor hours
    core_daily_hours = core_positions * CORE_SHIFT_HOURS
    extended_daily_hours = (extended_positions_per_shift * EXTENDED_AM_HOURS +
                           extended_positions_per_shift * EXTENDED_PM_HOURS)
    total_daily_hours = core_daily_hours + extended_daily_hours

    # Daily labor cost (using average teacher rate for simplicity)
    avg_rate = avg_teacher_rate  # Use teacher rate as baseline
    daily_labor_cost = total_daily_hours * avg_rate

    # Weekly (5 days) and monthly (4.33 weeks) costs
    weekly_labor_cost = daily_labor_cost * 5
    monthly_labor_cost = weekly_labor_cost * 4.33

    # Cost per child
    cost_per_child_monthly = monthly_labor_cost / total_children if total_children > 0 else 0

    labor_costs = {
        'available_staff': {
            'total': len(available_staff),
            'teachers': len(teachers),
            'aides': len(aides),
            'avg_teacher_rate': round(avg_teacher_rate, 2),
            'avg_aide_rate': round(avg_aide_rate, 2)
        },
        'shifts': {
            'core': {
                'hours': CORE_SHIFT_HOURS,
                'schedule': '8:30am - 3:30pm',
                'staff_needed': core_positions,
                'note': 'Single shift (under 8hr OT threshold)'
            },
            'extended_am': {
                'hours': EXTENDED_AM_HOURS,
                'schedule': '7:00am - 1:00pm',
                'staff_needed': extended_positions_per_shift,
                'note': 'Morning shift'
            },
            'extended_pm': {
                'hours': EXTENDED_PM_HOURS,
                'schedule': '12:30pm - 6:00pm',
                'staff_needed': extended_positions_per_shift,
                'note': 'Afternoon shift (30-min overlap for handoff)'
            }
        },
        'positions': {
            'core_total': core_positions,
            'extended_total': extended_total_positions,
            'grand_total': total_positions
        },
        'hours': {
            'daily': round(total_daily_hours, 1),
            'weekly': round(total_daily_hours * 5, 1)
        },
        'costs': {
            'daily': round(daily_labor_cost, 2),
            'weekly': round(weekly_labor_cost, 2),
            'monthly': round(monthly_labor_cost, 2),
            'cost_per_child_monthly': round(cost_per_child_monthly, 2)
        }
    }

    return {
        'inputs': {
            'total_children': total_children,
            'age_mix': age_mix,
            'schedule_mix': schedule_mix,
            'days_mix': days_mix
        },
        'distribution': distribution,
        'daily_attendance': daily_attendance,
        'schedule_summary': schedule_summary,
        'staff_requirements': staff_requirements,
        'labor_costs': labor_costs
    }

def calculate_daily_labor(core_infants, core_children, extended_infants, extended_children):
    """
    Calculate labor requirements for a single day based on actual enrollment counts.

    Args:
        core_infants: Number of infants in core hours programs
        core_children: Number of children (2+) in core hours programs
        extended_infants: Number of infants in extended hours programs
        extended_children: Number of children (2+) in extended hours programs

    Returns:
        dict with staff positions, hours, and costs
    """
    import math

    # Shift hours with 30-min buffer before and after
    CORE_SHIFT_HOURS = 7.0  # 8:30am-3:30pm (single shift, under 8hr OT)
    EXTENDED_AM_HOURS = 6.0  # 7:00am-1:00pm
    EXTENDED_PM_HOURS = 5.5  # 12:30pm-6:00pm

    # Staff needed based on ratios (infants 1:4, children 1:12)
    core_infant_staff = math.ceil(core_infants / 4) if core_infants > 0 else 0
    core_child_staff = math.ceil(core_children / 12) if core_children > 0 else 0
    extended_infant_staff = math.ceil(extended_infants / 4) if extended_infants > 0 else 0
    extended_child_staff = math.ceil(extended_children / 12) if extended_children > 0 else 0

    # Positions needed
    core_positions = core_infant_staff + core_child_staff
    extended_positions = extended_infant_staff + extended_child_staff

    # Hours calculation
    core_hours = core_positions * CORE_SHIFT_HOURS
    extended_am_hours = extended_positions * EXTENDED_AM_HOURS
    extended_pm_hours = extended_positions * EXTENDED_PM_HOURS
    total_hours = core_hours + extended_am_hours + extended_pm_hours

    # Get average rate from available staff
    available_staff = StaffMember.query.filter_by(is_available=True).all()
    teachers = [s for s in available_staff if PERMIT_LEVELS.get(s.permit_level, {}).get('rank', 0) >= 3]
    avg_rate = sum(s.hourly_rate for s in teachers) / len(teachers) if teachers else 25.00

    daily_cost = total_hours * avg_rate

    return {
        'core_staff': core_positions,
        'core_hours': core_hours,
        'extended_staff': extended_positions,
        'extended_am_hours': extended_am_hours,
        'extended_pm_hours': extended_pm_hours,
        'total_positions': core_positions + (extended_positions * 2),  # Extended needs AM + PM
        'total_hours': round(total_hours, 1),
        'daily_cost': round(daily_cost, 2),
        'avg_rate': round(avg_rate, 2)
    }


def calculate_per_child_expenses(settings, per_child_costs):
    """Calculate total variable expenses based on enrollment distribution and per-child rates."""
    total = 0.0
    breakdown = []
    for cost in per_child_costs:
        if not cost.is_active:
            continue
        age_pct = settings.infant_percent if cost.age_group_type == 'infant' else settings.child_percent
        sched_pct = settings.core_percent if cost.schedule_type == 'core' else settings.extended_percent
        bucket_count = settings.total_children * (age_pct / 100) * (sched_pct / 100)
        line_total = round(bucket_count * cost.monthly_rate, 2)
        total += line_total
        breakdown.append({
            'name': cost.name,
            'age_group_type': cost.age_group_type,
            'schedule_type': cost.schedule_type,
            'rate': cost.monthly_rate,
            'children': round(bucket_count, 1),
            'total': line_total
        })
    return round(total, 2), breakdown


# Routes
@app.route('/')
@app.route('/dashboard')
def dashboard():
    """Dashboard overview page - main landing page with high-level summaries"""
    settings = CapacitySettings.get_or_create()
    staff_count = StaffMember.query.filter_by(is_available=True).count()
    total_staff = StaffMember.query.count()
    return render_template('dashboard.html', settings=settings,
                         staff_count=staff_count, total_staff=total_staff)

@app.route('/dashboard/summary')
def dashboard_summary():
    """JSON endpoint providing aggregated data for dashboard"""
    settings = CapacitySettings.get_or_create()

    # Get capacity plan data
    age_mix = settings.get_age_mix()
    schedule_mix = settings.get_schedule_mix()
    days_mix = settings.get_days_mix()
    capacity_data = calculate_capacity_plan(age_mix, schedule_mix, days_mix, settings.total_children)

    # Staff counts
    available_staff = StaffMember.query.filter_by(is_available=True).all()
    teachers = [s for s in available_staff if PERMIT_LEVELS.get(s.permit_level, {}).get('rank', 0) >= 3]
    aides = [s for s in available_staff if PERMIT_LEVELS.get(s.permit_level, {}).get('rank', 0) < 3]

    # Get expenses
    fixed_expenses = FixedExpense.query.filter_by(is_active=True).all()
    total_fixed = sum(e.monthly_amount for e in fixed_expenses)

    per_child_costs = PerChildCost.query.filter_by(is_active=True).all()
    total_variable, _ = calculate_per_child_expenses(settings, per_child_costs)

    # Get labor costs from capacity data
    labor_monthly = capacity_data.get('labor_costs', {}).get('costs', {}).get('monthly', 0)
    total_monthly_cost = labor_monthly + total_fixed + total_variable

    # Get pricing info
    plans = CorePlan.query.filter_by(is_active=True).all()
    plan_prices = [p.base_price for p in plans if p.base_price > 0]
    min_price = min(plan_prices) if plan_prices else 0
    max_price = max(plan_prices) if plan_prices else 0

    # Calculate revenue potential (simplified: average price * total children * 4.33 weeks if weekly)
    avg_price = (min_price + max_price) / 2 if plan_prices else 0
    weekly_plans = [p for p in plans if p.billing_period == 'weekly']
    monthly_plans = [p for p in plans if p.billing_period == 'monthly']

    # Estimate revenue: assume mix of weekly and monthly
    if settings.total_children > 0 and plan_prices:
        avg_weekly = sum(p.base_price for p in weekly_plans) / len(weekly_plans) if weekly_plans else 0
        avg_monthly = sum(p.base_price for p in monthly_plans) / len(monthly_plans) if monthly_plans else avg_weekly * 4.33
        revenue_potential = avg_monthly * settings.total_children
    else:
        revenue_potential = 0

    return jsonify({
        'enrollment': {
            'total_children': settings.total_children,
            'age_mix': age_mix,
            'schedule_mix': schedule_mix,
            'peak_day': capacity_data.get('staff_requirements', {}).get('peak_day', 'Monday'),
            'peak_attendance': capacity_data.get('staff_requirements', {}).get('peak_total', 0),
            'daily_attendance': capacity_data.get('daily_attendance', {})
        },
        'staffing': {
            'available': len(available_staff),
            'total': StaffMember.query.count(),
            'teachers': len(teachers),
            'aides': len(aides),
            'teachers_needed': capacity_data.get('staff_requirements', {}).get('total_teachers_needed', 0),
            'is_adequate': len(teachers) >= capacity_data.get('staff_requirements', {}).get('total_teachers_needed', 0)
        },
        'financial': {
            'labor_cost': labor_monthly,
            'fixed_expenses': total_fixed,
            'variable_expenses': total_variable,
            'total_monthly_cost': total_monthly_cost,
            'revenue_potential': round(revenue_potential, 2),
            'net_margin': round(revenue_potential - total_monthly_cost, 2)
        },
        'pricing': {
            'plan_count': len(plans),
            'min_price': min_price,
            'max_price': max_price
        }
    })

@app.route('/age-groups')
def manage_age_groups():
    age_groups = AgeGroup.query.order_by(AgeGroup.min_age_months).all()
    return render_template('age_groups.html', age_groups=age_groups)

@app.route('/age-groups/add', methods=['POST'])
def add_age_group():
    import json
    data = request.form

    # Handle enhanced ratios from form
    enhanced_ratios = []
    if data.get('enhanced_ratios_json'):
        try:
            enhanced_ratios = json.loads(data['enhanced_ratios_json'])
        except:
            pass

    age_group = AgeGroup(
        name=data['name'],
        min_age_months=int(data['min_age_months']),
        max_age_months=int(data['max_age_months']),
        required_ratio=data['required_ratio'],
        enhanced_ratios=json.dumps(enhanced_ratios) if enhanced_ratios else None
    )
    db.session.add(age_group)
    db.session.commit()
    return redirect(url_for('manage_age_groups'))

@app.route('/age-groups/delete/<int:id>', methods=['POST'])
def delete_age_group(id):
    age_group = AgeGroup.query.get_or_404(id)
    db.session.delete(age_group)
    db.session.commit()
    return redirect(url_for('manage_age_groups'))

@app.route('/staff')
def manage_staff():
    staff = StaffMember.query.order_by(StaffMember.permit_level.desc(), StaffMember.name).all()
    return render_template('staff.html', staff=staff, permit_levels=list(PERMIT_LEVELS.keys()))

@app.route('/staff/add', methods=['POST'])
def add_staff():
    data = request.form
    staff = StaffMember(
        name=data['name'],
        permit_level=data['permit_level'],
        is_available=True,
        hourly_rate=float(data.get('hourly_rate', 0.0)),
        ece_units=int(data.get('ece_units', 0)),
        has_infant_specialization=data.get('has_infant_specialization') == 'on',
        is_fully_qualified=data.get('is_fully_qualified', 'on') == 'on',
        is_director=data.get('is_director') == 'on',
        director_counts_toward_ratio=data.get('director_counts_toward_ratio') == 'on'
    )
    db.session.add(staff)
    db.session.commit()
    return redirect(url_for('manage_staff'))

@app.route('/staff/toggle/<int:id>', methods=['POST'])
def toggle_staff_availability(id):
    staff = StaffMember.query.get_or_404(id)
    staff.is_available = not staff.is_available
    db.session.commit()
    return redirect(url_for('manage_staff'))

@app.route('/staff/delete/<int:id>', methods=['POST'])
def delete_staff(id):
    staff = StaffMember.query.get_or_404(id)
    db.session.delete(staff)
    db.session.commit()
    return redirect(url_for('manage_staff'))

@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.json
    results = calculate_staffing_needs(data['age_groups'])
    return jsonify(results)

@app.route('/pricing')
def manage_pricing():
    """Pricing management page"""
    age_groups = AgeGroup.query.all()
    core_plans = CorePlan.query.order_by(CorePlan.name).all()
    add_ons = AddOn.query.order_by(AddOn.name).all()
    fees = OneTimeFee.query.order_by(OneTimeFee.fee_type, OneTimeFee.name).all()
    discounts = Discount.query.order_by(Discount.name).all()

    return render_template('pricing.html',
                         age_groups=age_groups,
                         core_plans=core_plans,
                         add_ons=add_ons,
                         fees=fees,
                         discounts=discounts)

# Core Plan Routes
@app.route('/pricing/core-plan/add', methods=['POST'])
def add_core_plan():
    data = request.form
    plan = CorePlan(
        name=data['name'],
        description=data.get('description', ''),
        base_price=float(data['base_price']),
        billing_period=data['billing_period'],
        age_group_id=int(data['age_group_id']) if data.get('age_group_id') else None,
        monday=data.get('monday') == 'on',
        tuesday=data.get('tuesday') == 'on',
        wednesday=data.get('wednesday') == 'on',
        thursday=data.get('thursday') == 'on',
        friday=data.get('friday') == 'on',
        start_time=data.get('start_time', '9:00 AM'),
        end_time=data.get('end_time', '3:00 PM'),
        is_active=data.get('is_active') == 'on'
    )
    db.session.add(plan)
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/core-plan/delete/<int:id>', methods=['POST'])
def delete_core_plan(id):
    plan = CorePlan.query.get_or_404(id)
    db.session.delete(plan)
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/core-plan/toggle/<int:id>', methods=['POST'])
def toggle_core_plan(id):
    plan = CorePlan.query.get_or_404(id)
    plan.is_active = not plan.is_active
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/core-plan/edit/<int:id>', methods=['POST'])
def edit_core_plan(id):
    plan = CorePlan.query.get_or_404(id)
    data = request.form

    plan.name = data['name']
    plan.description = data.get('description', '')
    plan.base_price = float(data['base_price'])
    plan.billing_period = data['billing_period']
    plan.age_group_id = int(data['age_group_id']) if data.get('age_group_id') else None
    plan.monday = data.get('monday') == 'on'
    plan.tuesday = data.get('tuesday') == 'on'
    plan.wednesday = data.get('wednesday') == 'on'
    plan.thursday = data.get('thursday') == 'on'
    plan.friday = data.get('friday') == 'on'
    plan.start_time = data.get('start_time', '9:00 AM')
    plan.end_time = data.get('end_time', '3:00 PM')
    plan.is_active = data.get('is_active') == 'on'

    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/fixed-plans/update', methods=['POST'])
def update_fixed_plan_prices():
    """Bulk update prices for all 12 fixed plans"""
    data = request.form
    for key, value in data.items():
        if key.startswith('price_'):
            plan_id = int(key.replace('price_', ''))
            plan = CorePlan.query.get(plan_id)
            if plan and plan.is_fixed_plan:
                try:
                    plan.base_price = float(value)
                except ValueError:
                    pass
    db.session.commit()
    return redirect(url_for('manage_pricing'))

# Add-On Routes
@app.route('/pricing/add-on/add', methods=['POST'])
def add_addon():
    data = request.form
    addon = AddOn(
        name=data['name'],
        description=data.get('description', ''),
        pricing_type=data['pricing_type'],
        price=float(data['price']),
        minutes_unit=int(data.get('minutes_unit', 1)),
        is_extended_care=data.get('is_extended_care') == 'on',
        is_active=data.get('is_active') == 'on'
    )
    db.session.add(addon)
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/add-on/delete/<int:id>', methods=['POST'])
def delete_addon(id):
    addon = AddOn.query.get_or_404(id)
    db.session.delete(addon)
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/add-on/toggle/<int:id>', methods=['POST'])
def toggle_addon(id):
    addon = AddOn.query.get_or_404(id)
    addon.is_active = not addon.is_active
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/add-on/edit/<int:id>', methods=['POST'])
def edit_addon(id):
    addon = AddOn.query.get_or_404(id)
    data = request.form
    addon.name = data['name']
    addon.description = data.get('description', '')
    addon.pricing_type = data['pricing_type']
    addon.price = float(data['price'])
    addon.minutes_unit = int(data.get('minutes_unit', 1))
    addon.is_extended_care = data.get('is_extended_care') == 'on'
    addon.is_active = data.get('is_active') == 'on'
    db.session.commit()
    return redirect(url_for('manage_pricing'))

# One-Time Fee Routes
@app.route('/pricing/fee/add', methods=['POST'])
def add_fee():
    data = request.form
    fee = OneTimeFee(
        name=data['name'],
        description=data.get('description', ''),
        amount=float(data['amount']),
        fee_type=data['fee_type'],
        is_active=data.get('is_active') == 'on',
        is_refundable=data.get('is_refundable') == 'on'
    )
    db.session.add(fee)
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/fee/delete/<int:id>', methods=['POST'])
def delete_fee(id):
    fee = OneTimeFee.query.get_or_404(id)
    db.session.delete(fee)
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/fee/toggle/<int:id>', methods=['POST'])
def toggle_fee(id):
    fee = OneTimeFee.query.get_or_404(id)
    fee.is_active = not fee.is_active
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/fee/edit/<int:id>', methods=['POST'])
def edit_fee(id):
    fee = OneTimeFee.query.get_or_404(id)
    data = request.form
    fee.name = data['name']
    fee.description = data.get('description', '')
    fee.amount = float(data['amount'])
    fee.fee_type = data['fee_type']
    fee.is_refundable = data.get('is_refundable') == 'on'
    fee.is_active = data.get('is_active') == 'on'
    db.session.commit()
    return redirect(url_for('manage_pricing'))

# Discount Routes
@app.route('/pricing/discount/add', methods=['POST'])
def add_discount():
    data = request.form
    discount = Discount(
        name=data['name'],
        description=data.get('description', ''),
        discount_type=data['discount_type'],
        amount=float(data['amount']),
        applies_to=data['applies_to'],
        conditions=data.get('conditions', ''),
        is_active=data.get('is_active') == 'on'
    )
    db.session.add(discount)
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/discount/delete/<int:id>', methods=['POST'])
def delete_discount(id):
    discount = Discount.query.get_or_404(id)
    db.session.delete(discount)
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/discount/toggle/<int:id>', methods=['POST'])
def toggle_discount(id):
    discount = Discount.query.get_or_404(id)
    discount.is_active = not discount.is_active
    db.session.commit()
    return redirect(url_for('manage_pricing'))

@app.route('/pricing/discount/edit/<int:id>', methods=['POST'])
def edit_discount(id):
    discount = Discount.query.get_or_404(id)
    data = request.form
    discount.name = data['name']
    discount.description = data.get('description', '')
    discount.discount_type = data['discount_type']
    discount.amount = float(data['amount'])
    discount.applies_to = data['applies_to']
    discount.conditions = data.get('conditions', '')
    discount.is_active = data.get('is_active') == 'on'
    db.session.commit()
    return redirect(url_for('manage_pricing'))

# Package Routes
# Enrollment Routes
@app.route('/enrollment')
def manage_enrollment():
    """Redirect to capacity planner - enrollment is now managed via capacity settings"""
    return redirect(url_for('capacity_planner'))

@app.route('/enrollment/add', methods=['POST'])
def add_enrollment():
    data = request.form
    enrollment = Enrollment(
        enrollment_package_id=int(data['enrollment_package_id']),
        age_group_id=int(data['age_group_id']),
        child_count=int(data['child_count']),
        status=data.get('status', 'active'),
        notes=data.get('notes', '')
    )
    db.session.add(enrollment)
    db.session.commit()
    return redirect(url_for('manage_enrollment'))

@app.route('/enrollment/delete/<int:id>', methods=['POST'])
def delete_enrollment(id):
    enrollment = Enrollment.query.get_or_404(id)
    db.session.delete(enrollment)
    db.session.commit()
    return redirect(url_for('manage_enrollment'))

@app.route('/enrollment/toggle/<int:id>', methods=['POST'])
def toggle_enrollment_status(id):
    enrollment = Enrollment.query.get_or_404(id)
    enrollment.status = 'inactive' if enrollment.status == 'active' else 'active'
    db.session.commit()
    return redirect(url_for('manage_enrollment'))

@app.route('/enrollment/edit/<int:id>', methods=['POST'])
def edit_enrollment(id):
    enrollment = Enrollment.query.get_or_404(id)
    data = request.form
    enrollment.enrollment_package_id = int(data['enrollment_package_id'])
    enrollment.age_group_id = int(data['age_group_id'])
    enrollment.child_count = int(data['child_count'])
    enrollment.notes = data.get('notes', '')
    db.session.commit()
    return redirect(url_for('manage_enrollment'))

def time_str_to_minutes(time_str):
    """Convert '9:00 AM' to minutes since midnight (e.g., 540)"""
    import re
    match = re.match(r'(\d+):(\d+)\s*(AM|PM)', time_str, re.IGNORECASE)
    if not match:
        return 0
    hours, mins = int(match.group(1)), int(match.group(2))
    if match.group(3).upper() == 'PM' and hours != 12:
        hours += 12
    if match.group(3).upper() == 'AM' and hours == 12:
        hours = 0
    return hours * 60 + mins

# Schedule Routes
@app.route('/schedule')
def monthly_schedule():
    """View typical monthly schedule pattern - uses capacity settings as source of truth"""

    # Get capacity settings (source of truth for enrollment)
    settings = CapacitySettings.get_or_create()

    # Calculate the distribution from capacity settings
    capacity_data = calculate_capacity_plan(
        settings.get_age_mix(),
        settings.get_schedule_mix(),
        settings.get_days_mix(),
        settings.total_children
    )

    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    # Build schedule data from capacity plan
    schedule_data = {}
    for day_name in days_of_week:
        day_attendance = capacity_data['daily_attendance'].get(day_name, {'infants': 0, 'children': 0, 'total': 0})

        # For this day, get breakdown by schedule type
        # Use the schedule_summary to determine core vs extended split
        schedule_summary = capacity_data['schedule_summary']
        total_day = day_attendance['total']

        if total_day > 0:
            # Approximate core vs extended ratio from schedule_summary
            total_enrolled = schedule_summary['core']['total'] + schedule_summary['extended']['total']
            if total_enrolled > 0:
                core_ratio = schedule_summary['core']['total'] / total_enrolled
                extended_ratio = schedule_summary['extended']['total'] / total_enrolled
            else:
                core_ratio = 0.5
                extended_ratio = 0.5

            core_infants = int(day_attendance['infants'] * core_ratio)
            extended_infants = day_attendance['infants'] - core_infants
            core_children = int(day_attendance['children'] * core_ratio)
            extended_children = day_attendance['children'] - core_children
        else:
            core_infants = core_children = extended_infants = extended_children = 0

        # Calculate labor for this day
        labor = calculate_daily_labor(core_infants, core_children, extended_infants, extended_children)

        # Build enrollment-like items from distribution for display
        enrollments = []
        for dist in capacity_data['distribution']:
            # Check if this plan applies to this day
            day_pattern = dist['day_pattern']
            applies_to_day = False
            if day_pattern == 'full':
                applies_to_day = True
            elif day_pattern == 'mwf' and day_name in ['Monday', 'Wednesday', 'Friday']:
                applies_to_day = True
            elif day_pattern == 'tth' and day_name in ['Tuesday', 'Thursday']:
                applies_to_day = True

            if applies_to_day and dist['children'] > 0:
                enrollments.append({
                    'plan_name': dist['plan_name'],
                    'count': dist['children'],
                    'age_group_type': dist['age_group_type'],
                    'age_group_name': dist['age_group_name'],
                    'schedule_type': dist['schedule_type'],
                    'schedule_name': dist['schedule_name'],
                    'day_pattern_name': dist['day_pattern_name']
                })

        # Consolidate enrollments by age_group_type + schedule_type
        consolidated = {}
        for item in enrollments:
            key = (item['age_group_type'], item['schedule_type'])
            if key in consolidated:
                consolidated[key]['count'] += item['count']
            else:
                consolidated[key] = dict(item)
        enrollments = list(consolidated.values())

        # Build children array with times for detailed view
        children_detail = []
        for item in enrollments:
            start = '7:30 AM' if item['schedule_type'] == 'extended' else '9:00 AM'
            end = '5:30 PM' if item['schedule_type'] == 'extended' else '3:00 PM'
            children_detail.append({
                'count': item['count'],
                'age_group': item['age_group_name'],
                'age_group_type': item['age_group_type'],
                'schedule_type': item['schedule_type'],
                'start_time': start,
                'end_time': end,
                'start_minutes': time_str_to_minutes(start),
                'end_minutes': time_str_to_minutes(end)
            })

        # Build staff_shifts array for detailed view
        staff_shifts = []
        if labor['core_staff'] > 0:
            staff_shifts.append({
                'label': f"{labor['core_staff']} Core",
                'count': labor['core_staff'],
                'shift_type': 'core',
                'start_minutes': 510,   # 8:30 AM
                'end_minutes': 930      # 3:30 PM
            })
        if labor['extended_staff'] > 0:
            staff_shifts.append({
                'label': f"{labor['extended_staff']} Ext AM",
                'count': labor['extended_staff'],
                'shift_type': 'extended_am',
                'start_minutes': 420,   # 7:00 AM
                'end_minutes': 780      # 1:00 PM
            })
            staff_shifts.append({
                'label': f"{labor['extended_staff']} Ext PM",
                'count': labor['extended_staff'],
                'shift_type': 'extended_pm',
                'start_minutes': 750,   # 12:30 PM
                'end_minutes': 1080     # 6:00 PM
            })

        # Generate timeline data for visualization (15-minute intervals from 7:00 AM to 6:00 PM)
        # Time ranges (in minutes from midnight):
        # Extended students: 7:30 AM (450) - 5:30 PM (1050)
        # Core students: 9:00 AM (540) - 3:00 PM (900)
        # Extended AM staff: 7:00 AM (420) - 1:00 PM (780)
        # Core staff: 8:30 AM (510) - 3:30 PM (930)
        # Extended PM staff: 12:30 PM (750) - 6:00 PM (1080)

        intervals = []
        max_students = 0
        max_staff = 0

        # Count students and staff by type for this day
        core_students = core_infants + core_children
        extended_students = extended_infants + extended_children

        # Get staff counts from labor calculation
        core_staff_count = labor['core_staff']
        extended_staff_count = labor['extended_staff']

        for minutes in range(420, 1081, 15):  # 7:00 AM to 6:00 PM
            students = 0
            staff = 0

            # Extended students: 7:30 AM - 5:30 PM
            if 450 <= minutes < 1050:
                students += extended_students

            # Core students: 9:00 AM - 3:00 PM
            if 540 <= minutes < 900:
                students += core_students

            # Extended AM staff: 7:00 AM - 1:00 PM
            if 420 <= minutes < 780:
                staff += extended_staff_count

            # Core staff: 8:30 AM - 3:30 PM
            if 510 <= minutes < 930:
                staff += core_staff_count

            # Extended PM staff: 12:30 PM - 6:00 PM
            if 750 <= minutes < 1080:
                staff += extended_staff_count

            intervals.append({'time': minutes, 'students': students, 'staff': staff})
            max_students = max(max_students, students)
            max_staff = max(max_staff, staff)

        timeline = {
            'intervals': intervals,
            'earliest': 420,
            'latest': 1080,
            'max_students': max_students,
            'max_staff': max_staff
        }

        schedule_data[day_name] = {
            'day_name': day_name,
            'total_children': day_attendance['total'],
            'infants': day_attendance['infants'],
            'children': day_attendance['children'],
            'enrollments': enrollments,
            'labor': labor,
            'timeline': timeline,
            'children_detail': children_detail,
            'staff_shifts': staff_shifts
        }

    # Calculate weekly labor summary (use peak day for positions, sum for costs)
    peak_day = max(schedule_data.values(), key=lambda x: x['total_children'])
    peak_labor = peak_day['labor']

    # Sum daily costs across all 5 days
    total_weekly_cost = sum(d['labor']['daily_cost'] for d in schedule_data.values())

    weekly_labor = {
        'core_staff': peak_labor['core_staff'],
        'core_hours': peak_labor['core_hours'],
        'extended_staff': peak_labor['extended_staff'],
        'extended_am_hours': peak_labor['extended_am_hours'],
        'extended_pm_hours': peak_labor['extended_pm_hours'],
        'total_positions': peak_labor['total_positions'],
        'total_hours': peak_labor['total_hours'],
        'daily_cost': peak_labor['daily_cost'],
        'weekly_cost': round(total_weekly_cost, 2),
        'monthly_cost': round(total_weekly_cost * 4.33, 2),
        'avg_rate': peak_labor['avg_rate']
    }

    # Create a single week calendar structure for display
    calendar = [days_of_week[:]]

    return render_template('schedule_monthly.html',
                         month_name="Typical Month",
                         calendar=calendar,
                         schedule_data=schedule_data,
                         weekly_labor=weekly_labor,
                         capacity_data=capacity_data,
                         settings=settings,
                         age_groups=AgeGroup.query.all())

def format_time_12hr(time_str):
    """Convert time to 12-hour format like '9:00 AM'"""
    from datetime import datetime
    if not time_str:
        return ''

    # Handle formats like "08:00 AM" or "08:00" or "8:00 AM"
    try:
        # Try parsing with AM/PM first
        if 'AM' in time_str or 'PM' in time_str:
            dt = datetime.strptime(time_str.strip(), '%I:%M %p')
        else:
            dt = datetime.strptime(time_str.strip(), '%H:%M')

        # Format as "9:00 AM" (no leading zero for hour)
        return dt.strftime('%-I:%M %p' if dt.strftime('%p') else '%I:%M %p').lstrip('0')
    except:
        return time_str

@app.route('/schedule/daily/<day_name_str>')
def daily_schedule(day_name_str):
    """View detailed schedule for a specific day - uses capacity settings as source of truth"""
    import math

    # Validate day name
    valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    if day_name_str not in valid_days:
        return jsonify({'error': 'Invalid day name'}), 400

    # Get capacity settings (source of truth)
    settings = CapacitySettings.get_or_create()
    capacity_data = calculate_capacity_plan(
        settings.get_age_mix(),
        settings.get_schedule_mix(),
        settings.get_days_mix(),
        settings.total_children
    )

    # Get attendance for this day
    day_attendance = capacity_data['daily_attendance'].get(day_name_str, {'infants': 0, 'children': 0, 'total': 0})

    # Build list of enrollments for this day from distribution
    attending = []
    for dist in capacity_data['distribution']:
        # Check if this plan applies to this day
        day_pattern = dist['day_pattern']
        applies_to_day = False
        if day_pattern == 'full':
            applies_to_day = True
        elif day_pattern == 'mwf' and day_name_str in ['Monday', 'Wednesday', 'Friday']:
            applies_to_day = True
        elif day_pattern == 'tth' and day_name_str in ['Tuesday', 'Thursday']:
            applies_to_day = True

        if applies_to_day and dist['children'] > 0:
            # Get times based on schedule type
            if dist['schedule_type'] == 'extended':
                start_time = '7:30 AM'
                end_time = '5:30 PM'
            else:
                start_time = '9:00 AM'
                end_time = '3:00 PM'

            attending.append({
                'count': dist['children'],
                'age_group': dist['age_group_name'],
                'age_group_type': dist['age_group_type'],
                'schedule_type': dist['schedule_type'],
                'start_time': start_time,
                'end_time': end_time,
                'package_name': f"{dist['schedule_name'][:4]} {dist['day_pattern_name']}"
            })

    # Consolidate by age_group_type + schedule_type
    consolidated = {}
    for item in attending:
        key = (item['age_group_type'], item['schedule_type'])
        if key in consolidated:
            consolidated[key]['count'] += item['count']
        else:
            consolidated[key] = dict(item)
            consolidated[key]['package_name'] = item['schedule_type'].title()
    attending = list(consolidated.values())

    # Calculate age group breakdown
    infant_count = day_attendance['infants']
    child_count = day_attendance['children']

    age_group_breakdown = []
    if infant_count > 0:
        infant_staff = math.ceil(infant_count / 4)
        age_group_breakdown.append({
            'name': 'Infants (0-18 months)',
            'ratio': '1:4',
            'count': infant_count,
            'required_staff': infant_staff
        })
    if child_count > 0:
        child_staff = math.ceil(child_count / 12)
        age_group_breakdown.append({
            'name': 'Child (2-6 years)',
            'ratio': '1:12',
            'count': child_count,
            'required_staff': child_staff
        })

    total_staff = sum(ag['required_staff'] for ag in age_group_breakdown)

    # Calculate labor/shift data for staff coverage overlay
    # Determine core vs extended split for this day
    core_infants = 0
    core_children = 0
    extended_infants = 0
    extended_children = 0
    for item in attending:
        is_infant = item['age_group_type'] == 'infant'
        is_extended = item['schedule_type'] == 'extended'
        if is_extended:
            if is_infant:
                extended_infants += item['count']
            else:
                extended_children += item['count']
        else:
            if is_infant:
                core_infants += item['count']
            else:
                core_children += item['count']

    labor = calculate_daily_labor(core_infants, core_children, extended_infants, extended_children)

    # Build staff shift bars for timeline
    staff_shifts = []
    if labor['core_staff'] > 0:
        staff_shifts.append({
            'label': f"{labor['core_staff']} Core Staff",
            'count': labor['core_staff'],
            'start_time': '8:30 AM',
            'end_time': '3:30 PM',
            'shift_type': 'core'
        })
    if labor['extended_staff'] > 0:
        staff_shifts.append({
            'label': f"{labor['extended_staff']} Extended AM Staff",
            'count': labor['extended_staff'],
            'start_time': '7:00 AM',
            'end_time': '1:00 PM',
            'shift_type': 'extended_am'
        })
        staff_shifts.append({
            'label': f"{labor['extended_staff']} Extended PM Staff",
            'count': labor['extended_staff'],
            'start_time': '12:30 PM',
            'end_time': '6:00 PM',
            'shift_type': 'extended_pm'
        })

    return jsonify({
        'day_name': day_name_str,
        'total_children': day_attendance['total'],
        'infant_count': infant_count,
        'child_count': child_count,
        'children': attending,
        'age_group_breakdown': age_group_breakdown,
        'total_staff_required': total_staff,
        'labor': labor,
        'staff_shifts': staff_shifts
    })

# Capacity Planner Routes
@app.route('/capacity-planner')
def capacity_planner():
    """Capacity planning - source of truth for enrollment distribution"""
    settings = CapacitySettings.get_or_create()
    return render_template('capacity_planner.html',
                         schedule_types=SCHEDULE_TYPES,
                         day_patterns=DAY_PATTERNS,
                         age_group_types=AGE_GROUP_TYPES,
                         settings=settings)

@app.route('/capacity-planner/settings', methods=['GET'])
def get_capacity_settings():
    """Get current capacity settings"""
    settings = CapacitySettings.get_or_create()
    return jsonify({
        'total_children': settings.total_children,
        'max_capacity': settings.max_capacity if settings.max_capacity else 100,
        'age_mix': settings.get_age_mix(),
        'schedule_mix': settings.get_schedule_mix(),
        'days_mix': settings.get_days_mix()
    })

@app.route('/capacity-planner/settings', methods=['POST'])
def save_capacity_settings():
    """Save capacity settings - this updates the source of truth for enrollment"""
    data = request.json

    age_mix = data.get('age_mix', {'infant': 20, 'child': 80})
    schedule_mix = data.get('schedule_mix', {'core': 50, 'extended': 50})
    days_mix = data.get('days_mix', {'full': 60, 'mwf': 30, 'tth': 10})
    total_children = data.get('total_children', 50)
    max_capacity = data.get('max_capacity', 100)

    # Validate that each mix totals 100
    if abs(sum(age_mix.values()) - 100) > 0.01:
        return jsonify({'error': 'Age mix must total 100%'}), 400
    if abs(sum(schedule_mix.values()) - 100) > 0.01:
        return jsonify({'error': 'Schedule mix must total 100%'}), 400
    if abs(sum(days_mix.values()) - 100) > 0.01:
        return jsonify({'error': 'Days mix must total 100%'}), 400

    # Update settings
    settings = CapacitySettings.get_or_create()
    settings.total_children = total_children
    settings.max_capacity = max_capacity
    settings.infant_percent = age_mix.get('infant', 20)
    settings.child_percent = age_mix.get('child', 80)
    settings.core_percent = schedule_mix.get('core', 50)
    settings.extended_percent = schedule_mix.get('extended', 50)
    settings.full_percent = days_mix.get('full', 60)
    settings.mwf_percent = days_mix.get('mwf', 30)
    settings.tth_percent = days_mix.get('tth', 10)

    db.session.commit()

    return jsonify({'success': True, 'message': 'Settings saved'})

@app.route('/capacity-planner/calculate', methods=['POST'])
def calculate_capacity():
    """Calculate capacity plan from ratios and optionally save"""
    data = request.json

    # Validate inputs
    age_mix = data.get('age_mix', {'infant': 20, 'child': 80})
    schedule_mix = data.get('schedule_mix', {'core': 50, 'extended': 50})
    days_mix = data.get('days_mix', {'full': 60, 'mwf': 30, 'tth': 10})
    total_children = data.get('total_children', 50)

    # Validate that each mix totals 100
    if abs(sum(age_mix.values()) - 100) > 0.01:
        return jsonify({'error': 'Age mix must total 100%'}), 400
    if abs(sum(schedule_mix.values()) - 100) > 0.01:
        return jsonify({'error': 'Schedule mix must total 100%'}), 400
    if abs(sum(days_mix.values()) - 100) > 0.01:
        return jsonify({'error': 'Days mix must total 100%'}), 400

    # Auto-save settings when calculating
    settings = CapacitySettings.get_or_create()
    settings.total_children = total_children
    settings.infant_percent = age_mix.get('infant', 20)
    settings.child_percent = age_mix.get('child', 80)
    settings.core_percent = schedule_mix.get('core', 50)
    settings.extended_percent = schedule_mix.get('extended', 50)
    settings.full_percent = days_mix.get('full', 60)
    settings.mwf_percent = days_mix.get('mwf', 30)
    settings.tth_percent = days_mix.get('tth', 10)
    db.session.commit()

    results = calculate_capacity_plan(age_mix, schedule_mix, days_mix, total_children)
    return jsonify(results)


# Expense routes
@app.route('/expenses')
def manage_expenses():
    fixed_expenses = FixedExpense.query.order_by(FixedExpense.category, FixedExpense.name).all()
    per_child_costs = PerChildCost.query.order_by(PerChildCost.name, PerChildCost.age_group_type, PerChildCost.schedule_type).all()
    settings = CapacitySettings.get_or_create()

    # Group fixed expenses by category
    grouped_fixed = {}
    for cat_key, cat_label in EXPENSE_CATEGORIES.items():
        items = [e for e in fixed_expenses if e.category == cat_key]
        if items:
            grouped_fixed[cat_key] = {
                'label': cat_label,
                'expenses': items,
                'subtotal': sum(e.monthly_amount for e in items if e.is_active)
            }

    # Group per-child costs by name
    grouped_per_child = {}
    for cost in per_child_costs:
        if cost.name not in grouped_per_child:
            grouped_per_child[cost.name] = {
                'description': cost.description,
                'is_active': cost.is_active,
                'rates': {}
            }
        grouped_per_child[cost.name]['rates'][(cost.age_group_type, cost.schedule_type)] = cost.monthly_rate

    total_fixed = sum(e.monthly_amount for e in fixed_expenses if e.is_active)
    total_variable, variable_breakdown = calculate_per_child_expenses(settings, per_child_costs)
    grand_total = total_fixed + total_variable
    total_children = settings.total_children if settings.total_children > 0 else 1
    per_child_monthly = round(grand_total / total_children, 2)

    return render_template('expenses.html',
                         grouped_fixed=grouped_fixed,
                         grouped_per_child=grouped_per_child,
                         variable_breakdown=variable_breakdown,
                         total_fixed=total_fixed,
                         total_variable=total_variable,
                         grand_total=grand_total,
                         per_child_monthly=per_child_monthly,
                         settings=settings,
                         expense_categories=EXPENSE_CATEGORIES,
                         age_group_types=AGE_GROUP_TYPES,
                         schedule_types=SCHEDULE_TYPES)


@app.route('/expenses/fixed/add', methods=['POST'])
def add_fixed_expense():
    expense = FixedExpense(
        name=request.form['name'],
        category=request.form['category'],
        monthly_amount=float(request.form['monthly_amount']),
        description=request.form.get('description', ''),
        is_active=True
    )
    db.session.add(expense)
    db.session.commit()
    return redirect(url_for('manage_expenses'))


@app.route('/expenses/fixed/edit/<int:id>', methods=['POST'])
def edit_fixed_expense(id):
    expense = FixedExpense.query.get_or_404(id)
    expense.name = request.form['name']
    expense.category = request.form['category']
    expense.monthly_amount = float(request.form['monthly_amount'])
    expense.description = request.form.get('description', '')
    db.session.commit()
    return redirect(url_for('manage_expenses'))


@app.route('/expenses/fixed/delete/<int:id>', methods=['POST'])
def delete_fixed_expense(id):
    expense = FixedExpense.query.get_or_404(id)
    db.session.delete(expense)
    db.session.commit()
    return redirect(url_for('manage_expenses'))


@app.route('/expenses/fixed/toggle/<int:id>', methods=['POST'])
def toggle_fixed_expense(id):
    expense = FixedExpense.query.get_or_404(id)
    expense.is_active = not expense.is_active
    db.session.commit()
    return redirect(url_for('manage_expenses'))


@app.route('/expenses/per-child/add', methods=['POST'])
def add_per_child_cost():
    name = request.form['name']
    description = request.form.get('description', '')
    for age in ['infant', 'child']:
        for sched in ['core', 'extended']:
            rate = float(request.form.get(f'rate_{age}_{sched}', 0))
            cost = PerChildCost(
                name=name,
                age_group_type=age,
                schedule_type=sched,
                monthly_rate=rate,
                description=description,
                is_active=True
            )
            db.session.add(cost)
    db.session.commit()
    return redirect(url_for('manage_expenses'))


@app.route('/expenses/per-child/edit/<name>', methods=['POST'])
def edit_per_child_cost(name):
    costs = PerChildCost.query.filter_by(name=name).all()
    new_name = request.form.get('name', name)
    description = request.form.get('description', '')
    for cost in costs:
        cost.name = new_name
        cost.description = description
        cost.monthly_rate = float(request.form.get(f'rate_{cost.age_group_type}_{cost.schedule_type}', cost.monthly_rate))
    db.session.commit()
    return redirect(url_for('manage_expenses'))


@app.route('/expenses/per-child/delete/<name>', methods=['POST'])
def delete_per_child_cost(name):
    PerChildCost.query.filter_by(name=name).delete()
    db.session.commit()
    return redirect(url_for('manage_expenses'))


@app.route('/expenses/per-child/toggle/<name>', methods=['POST'])
def toggle_per_child_cost(name):
    costs = PerChildCost.query.filter_by(name=name).all()
    if costs:
        new_state = not costs[0].is_active
        for cost in costs:
            cost.is_active = new_state
    db.session.commit()
    return redirect(url_for('manage_expenses'))


@app.route('/expenses/calculate')
def calculate_expenses():
    """JSON endpoint for capacity planner integration"""
    settings = CapacitySettings.get_or_create()
    fixed_expenses = FixedExpense.query.filter_by(is_active=True).all()
    per_child_costs = PerChildCost.query.all()

    total_fixed = sum(e.monthly_amount for e in fixed_expenses)
    total_variable, breakdown = calculate_per_child_expenses(settings, per_child_costs)
    grand_total = total_fixed + total_variable
    total_children = settings.total_children if settings.total_children > 0 else 1

    return jsonify({
        'total_fixed': round(total_fixed, 2),
        'total_variable': round(total_variable, 2),
        'grand_total': round(grand_total, 2),
        'per_child_monthly': round(grand_total / total_children, 2),
        'variable_breakdown': breakdown
    })


# ==================== PROJECTIONS ====================

def calculate_revenue_by_plan(settings):
    """
    Calculate monthly revenue based on enrollment distribution and plan prices.
    Returns detailed breakdown by plan combination.
    """
    plans = CorePlan.query.filter_by(is_active=True, is_fixed_plan=True).all()
    plan_lookup = {}
    for plan in plans:
        key = (plan.schedule_type, plan.day_pattern, plan.age_group_type)
        plan_lookup[key] = plan

    age_ratios = {'infant': settings.infant_percent / 100, 'child': settings.child_percent / 100}
    schedule_ratios = {'core': settings.core_percent / 100, 'extended': settings.extended_percent / 100}
    days_ratios = {'full': settings.full_percent / 100, 'mwf': settings.mwf_percent / 100, 'tth': settings.tth_percent / 100}

    revenue_breakdown = []
    total_revenue = 0.0

    for schedule_type in ['core', 'extended']:
        for day_pattern in ['full', 'mwf', 'tth']:
            for age_group_type in ['infant', 'child']:
                raw_count = (
                    settings.total_children *
                    age_ratios.get(age_group_type, 0) *
                    schedule_ratios.get(schedule_type, 0) *
                    days_ratios.get(day_pattern, 0)
                )
                child_count = round(raw_count)

                key = (schedule_type, day_pattern, age_group_type)
                plan = plan_lookup.get(key)
                price = plan.base_price if plan else 0

                line_revenue = child_count * price
                total_revenue += line_revenue

                if child_count > 0:
                    revenue_breakdown.append({
                        'schedule_type': schedule_type,
                        'day_pattern': day_pattern,
                        'age_group_type': age_group_type,
                        'plan_name': plan.name if plan else 'Unknown',
                        'children': child_count,
                        'price': price,
                        'revenue': round(line_revenue, 2)
                    })

    return round(total_revenue, 2), revenue_breakdown


def calculate_projections():
    """
    Calculate comprehensive financial projections.
    Returns P&L, break-even, and key metrics.
    """
    import math
    settings = CapacitySettings.get_or_create()

    # Revenue calculation
    monthly_revenue, revenue_breakdown = calculate_revenue_by_plan(settings)

    # Expense calculations
    fixed_expenses = FixedExpense.query.filter_by(is_active=True).all()
    total_fixed = sum(e.monthly_amount for e in fixed_expenses)
    fixed_by_category = {}
    for e in fixed_expenses:
        cat = EXPENSE_CATEGORIES.get(e.category, e.category)
        fixed_by_category[cat] = fixed_by_category.get(cat, 0) + e.monthly_amount

    per_child_costs = PerChildCost.query.filter_by(is_active=True).all()
    total_variable, variable_breakdown = calculate_per_child_expenses(settings, per_child_costs)

    # Labor costs
    age_mix = settings.get_age_mix()
    schedule_mix = settings.get_schedule_mix()
    days_mix = settings.get_days_mix()
    capacity_data = calculate_capacity_plan(age_mix, schedule_mix, days_mix, settings.total_children)
    labor_monthly = capacity_data.get('labor_costs', {}).get('costs', {}).get('monthly', 0)

    # Total expenses
    total_expenses = labor_monthly + total_fixed + total_variable

    # Profit calculations
    monthly_profit = monthly_revenue - total_expenses
    annual_revenue = monthly_revenue * 12
    annual_expenses = total_expenses * 12
    annual_profit = monthly_profit * 12

    # Margin calculations
    profit_margin_pct = (monthly_profit / monthly_revenue * 100) if monthly_revenue > 0 else 0
    labor_pct_of_revenue = (labor_monthly / monthly_revenue * 100) if monthly_revenue > 0 else 0

    # Revenue per child
    revenue_per_child = monthly_revenue / settings.total_children if settings.total_children > 0 else 0
    cost_per_child = total_expenses / settings.total_children if settings.total_children > 0 else 0

    # Break-even calculation
    # Fixed costs that don't scale with enrollment: fixed expenses
    # Variable costs that scale: labor + per-child costs
    if settings.total_children > 0:
        variable_cost_per_child = (labor_monthly + total_variable) / settings.total_children
    else:
        variable_cost_per_child = 0

    if revenue_per_child > variable_cost_per_child:
        break_even_children = math.ceil(total_fixed / (revenue_per_child - variable_cost_per_child))
    else:
        break_even_children = 0  # Cannot break even

    # Capacity utilization based on licensed capacity
    max_capacity = settings.max_capacity if settings.max_capacity else 100
    utilization_pct = (settings.total_children / max_capacity * 100) if max_capacity > 0 else 0

    return {
        'summary': {
            'monthly_revenue': round(monthly_revenue, 2),
            'monthly_expenses': round(total_expenses, 2),
            'monthly_profit': round(monthly_profit, 2),
            'annual_revenue': round(annual_revenue, 2),
            'annual_expenses': round(annual_expenses, 2),
            'annual_profit': round(annual_profit, 2),
            'profit_margin_pct': round(profit_margin_pct, 1),
            'is_profitable': monthly_profit > 0
        },
        'revenue': {
            'total': round(monthly_revenue, 2),
            'breakdown': revenue_breakdown,
            'per_child': round(revenue_per_child, 2)
        },
        'expenses': {
            'labor': round(labor_monthly, 2),
            'fixed': round(total_fixed, 2),
            'variable': round(total_variable, 2),
            'total': round(total_expenses, 2),
            'fixed_by_category': {k: round(v, 2) for k, v in fixed_by_category.items()},
            'variable_breakdown': variable_breakdown,
            'per_child': round(cost_per_child, 2)
        },
        'metrics': {
            'labor_pct_of_revenue': round(labor_pct_of_revenue, 1),
            'revenue_per_child': round(revenue_per_child, 2),
            'cost_per_child': round(cost_per_child, 2),
            'break_even_children': break_even_children,
            'current_enrollment': settings.total_children,
            'utilization_pct': round(utilization_pct, 1),
            'margin_above_break_even': settings.total_children - break_even_children
        },
        'enrollment': {
            'total': settings.total_children,
            'infant_pct': settings.infant_percent,
            'child_pct': settings.child_percent,
            'core_pct': settings.core_percent,
            'extended_pct': settings.extended_percent
        }
    }


def calculate_sensitivity(base_projections, variable, change_pct):
    """
    Calculate how profit changes with a given variable change.
    variable: 'enrollment', 'price', 'labor', 'fixed_expenses'
    change_pct: percentage change (e.g., 10 for +10%, -20 for -20%)
    """
    settings = CapacitySettings.get_or_create()
    multiplier = 1 + (change_pct / 100)

    if variable == 'enrollment':
        # More children = more revenue, more variable costs
        new_revenue = base_projections['revenue']['total'] * multiplier
        new_variable = base_projections['expenses']['variable'] * multiplier
        # Labor scales somewhat with enrollment (simplified)
        new_labor = base_projections['expenses']['labor'] * multiplier
        new_expenses = new_labor + base_projections['expenses']['fixed'] + new_variable
    elif variable == 'price':
        # Price change only affects revenue
        new_revenue = base_projections['revenue']['total'] * multiplier
        new_expenses = base_projections['expenses']['total']
    elif variable == 'labor':
        # Labor cost change only affects expenses
        new_revenue = base_projections['revenue']['total']
        new_labor = base_projections['expenses']['labor'] * multiplier
        new_expenses = new_labor + base_projections['expenses']['fixed'] + base_projections['expenses']['variable']
    elif variable == 'fixed_expenses':
        # Fixed expense change
        new_revenue = base_projections['revenue']['total']
        new_fixed = base_projections['expenses']['fixed'] * multiplier
        new_expenses = base_projections['expenses']['labor'] + new_fixed + base_projections['expenses']['variable']
    else:
        return None

    new_profit = new_revenue - new_expenses
    profit_change = new_profit - base_projections['summary']['monthly_profit']

    return {
        'variable': variable,
        'change_pct': change_pct,
        'new_revenue': round(new_revenue, 2),
        'new_expenses': round(new_expenses, 2),
        'new_profit': round(new_profit, 2),
        'profit_change': round(profit_change, 2),
        'is_profitable': new_profit > 0
    }


@app.route('/projections')
def projections():
    """Financial projections and analysis page"""
    settings = CapacitySettings.get_or_create()
    return render_template('projections.html', settings=settings)


@app.route('/projections/data')
def projections_data():
    """JSON endpoint for projections data"""
    projections = calculate_projections()
    return jsonify(projections)


@app.route('/projections/sensitivity')
def projections_sensitivity():
    """JSON endpoint for sensitivity analysis"""
    base = calculate_projections()

    # Calculate sensitivity for different scenarios
    scenarios = []
    for variable in ['enrollment', 'price', 'labor', 'fixed_expenses']:
        var_scenarios = []
        for change in [-20, -10, 0, 10, 20]:
            result = calculate_sensitivity(base, variable, change)
            if result:
                var_scenarios.append(result)
        scenarios.append({
            'variable': variable,
            'scenarios': var_scenarios
        })

    return jsonify({
        'base': base,
        'sensitivity': scenarios
    })


def run_migrations():
    """Run database migrations for schema changes"""
    with db.engine.connect() as conn:
        # Check if max_capacity column exists in capacity_settings
        result = conn.execute(db.text("PRAGMA table_info(capacity_settings)"))
        columns = [row[1] for row in result.fetchall()]
        if 'max_capacity' not in columns:
            conn.execute(db.text("ALTER TABLE capacity_settings ADD COLUMN max_capacity INTEGER DEFAULT 100"))
            conn.commit()


@app.route('/initialize-db')
def initialize_db():
    """Initialize database with sample data"""
    import json
    db.create_all()
    run_migrations()

    # Add sample age groups if none exist
    if AgeGroup.query.count() == 0:
        # Infants - basic ratio only (no enhanced options per CA regulations)
        infant_group = AgeGroup(
            name='Infants (0-18 months)',
            min_age_months=0,
            max_age_months=18,
            required_ratio='1:4',
            enhanced_ratios=None
        )

        # Toddlers - basic ratio only
        toddler_group = AgeGroup(
            name='Toddlers (18-30 months)',
            min_age_months=18,
            max_age_months=30,
            required_ratio='1:6',
            enhanced_ratios=None
        )

        # Child (2-6 years) - with enhanced ratio options
        child_enhanced = [
            {
                'ratio': '1:15',
                'description': '1 teacher + 1 aide',
                'requires_teachers': 1,
                'requires_aides': 1,
                'aide_min_ece_units': 0
            },
            {
                'ratio': '1:18',
                'description': '1 teacher + 1 aide with 6+ ECE units',
                'requires_teachers': 1,
                'requires_aides': 1,
                'aide_min_ece_units': 6
            }
        ]
        child_group = AgeGroup(
            name='Child (2-6 years)',
            min_age_months=24,
            max_age_months=72,
            required_ratio='1:12',
            enhanced_ratios=json.dumps(child_enhanced)
        )

        sample_groups = [infant_group, toddler_group, child_group]
        for group in sample_groups:
            db.session.add(group)
        db.session.commit()

    # Create the 12 fixed plans
    created_plans = create_fixed_plans()

    # Deactivate any legacy plans that aren't fixed plans
    legacy_plans = CorePlan.query.filter_by(is_fixed_plan=False).all()
    for plan in legacy_plans:
        plan.is_active = False
    db.session.commit()

    # Add add-ons if none exist
    if AddOn.query.count() == 0:
        kellys_corner = AddOn(
            name="Kelly's Corner",
            description='',
            pricing_type='per_day',
            price=10.0,
            minutes_unit=1,
            is_extended_care=False,
            is_active=True
        )
        db.session.add(kellys_corner)
        db.session.commit()

    # Deactivate any Extended Care add-ons (extended care is now built into plans)
    extended_care_addons = AddOn.query.filter_by(is_extended_care=True).all()
    for addon in extended_care_addons:
        addon.is_active = False
    db.session.commit()

    # Add one-time fees if none exist
    if OneTimeFee.query.count() == 0:
        registration_fee = OneTimeFee(
            name='Registration',
            description='Annual registration fee',
            amount=100.0,
            fee_type='registration',
            is_active=True,
            is_refundable=False
        )
        db.session.add(registration_fee)
        db.session.commit()

    # Add discounts if none exist
    if Discount.query.count() == 0:
        sibling_discount = Discount(
            name='Sibling',
            description='Discount for additional siblings',
            discount_type='percentage',
            amount=10.0,
            applies_to='core_plan',
            conditions='Applied to 2nd child and beyond',
            is_active=True
        )
        db.session.add(sibling_discount)
        db.session.commit()

    # Add placeholder staff if none exist
    if StaffMember.query.count() == 0:
        placeholder_staff = [
            # Teachers (can work alone, $28-35/hr)
            StaffMember(name='Teacher 1', permit_level='Teacher', hourly_rate=30.00,
                        ece_units=24, has_infant_specialization=True, is_fully_qualified=True),
            StaffMember(name='Teacher 2', permit_level='Teacher', hourly_rate=28.00,
                        ece_units=18, has_infant_specialization=False, is_fully_qualified=True),
            # Associate Teachers ($22-26/hr)
            StaffMember(name='Associate 1', permit_level='Associate Teacher', hourly_rate=24.00,
                        ece_units=12, has_infant_specialization=True, is_fully_qualified=True),
            StaffMember(name='Associate 2', permit_level='Associate Teacher', hourly_rate=22.00,
                        ece_units=12, has_infant_specialization=False, is_fully_qualified=True),
            # Assistants (need supervision, $18-20/hr)
            StaffMember(name='Assistant 1', permit_level='Assistant', hourly_rate=20.00,
                        ece_units=6, has_infant_specialization=False, is_fully_qualified=False),
            StaffMember(name='Assistant 2', permit_level='Assistant', hourly_rate=18.00,
                        ece_units=0, has_infant_specialization=False, is_fully_qualified=False),
        ]
        for staff in placeholder_staff:
            db.session.add(staff)
        db.session.commit()

    # Add default fixed expenses if none exist
    if FixedExpense.query.count() == 0:
        default_fixed = [
            FixedExpense(name='Electric', category='utility', monthly_amount=350.00, description='Monthly electric bill'),
            FixedExpense(name='Water', category='utility', monthly_amount=120.00, description='Monthly water bill'),
            FixedExpense(name='Gas', category='utility', monthly_amount=80.00, description='Monthly gas bill'),
            FixedExpense(name='Trash', category='utility', monthly_amount=75.00, description='Monthly trash pickup'),
            FixedExpense(name='Internet', category='utility', monthly_amount=100.00, description='Monthly internet service'),
            FixedExpense(name='Monthly Rent', category='lease', monthly_amount=4500.00, description='Monthly facility lease'),
            FixedExpense(name='Bookkeeping', category='professional', monthly_amount=500.00, description='Monthly bookkeeping service'),
        ]
        for expense in default_fixed:
            db.session.add(expense)
        db.session.commit()

    # Add default per-child costs if none exist
    if PerChildCost.query.count() == 0:
        supplies_rates = {
            ('infant', 'core'): 50.00,
            ('infant', 'extended'): 65.00,
            ('child', 'core'): 40.00,
            ('child', 'extended'): 50.00,
        }
        food_rates = {
            ('infant', 'core'): 75.00,
            ('infant', 'extended'): 100.00,
            ('child', 'core'): 60.00,
            ('child', 'extended'): 80.00,
        }
        for (age, sched), rate in supplies_rates.items():
            db.session.add(PerChildCost(name='Supplies', age_group_type=age, schedule_type=sched,
                                        monthly_rate=rate, description='Classroom and art supplies'))
        for (age, sched), rate in food_rates.items():
            db.session.add(PerChildCost(name='Snacks/Food', age_group_type=age, schedule_type=sched,
                                        monthly_rate=rate, description='Daily snacks and food'))
        db.session.commit()

    return f"Database initialized. Created {len(created_plans)} fixed plans."

# Initialize database when module is imported (for gunicorn/production)
with app.app_context():
    initialize_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
