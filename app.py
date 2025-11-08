from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///staffing.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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
    monday = db.Column(db.Boolean, default=True)
    tuesday = db.Column(db.Boolean, default=True)
    wednesday = db.Column(db.Boolean, default=True)
    thursday = db.Column(db.Boolean, default=True)
    friday = db.Column(db.Boolean, default=True)
    start_time = db.Column(db.String(10), default='9:00 AM')  # e.g., "9:00 AM"
    end_time = db.Column(db.String(10), default='3:00 PM')  # e.g., "3:00 PM"
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_days_selected(self):
        """Returns list of selected day names"""
        days = []
        if self.monday: days.append('Mon')
        if self.tuesday: days.append('Tue')
        if self.wednesday: days.append('Wed')
        if self.thursday: days.append('Thu')
        if self.friday: days.append('Fri')
        return days

    def get_days_count(self):
        """Returns number of days selected"""
        return len(self.get_days_selected())

    def get_schedule_display(self):
        """Returns formatted schedule like 'Mon, Wed, Fri 9:00 AM - 3:00 PM'"""
        days_str = ', '.join(self.get_days_selected())
        return f"{days_str} {self.start_time} - {self.end_time}"

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
    """Bulk enrollment tracking - number of children in a package"""
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

# Routes
@app.route('/')
def index():
    age_groups = AgeGroup.query.order_by(AgeGroup.min_age_months).all()
    staff = StaffMember.query.order_by(StaffMember.permit_level.desc()).all()
    return render_template('index.html',
                         age_groups=age_groups,
                         staff=staff,
                         permit_levels=PERMIT_LEVELS)

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

@app.route('/pricing/calculator')
def pricing_calculator():
    """Family-facing pricing calculator"""
    core_plans = CorePlan.query.filter_by(is_active=True).order_by(CorePlan.base_price).all()
    add_ons = AddOn.query.filter_by(is_active=True).order_by(AddOn.name).all()
    fees = OneTimeFee.query.filter_by(is_active=True).order_by(OneTimeFee.fee_type).all()
    discounts = Discount.query.filter_by(is_active=True).order_by(Discount.name).all()
    age_groups = AgeGroup.query.all()

    return render_template('pricing_calculator.html',
                         core_plans=core_plans,
                         add_ons=add_ons,
                         fees=fees,
                         discounts=discounts,
                         age_groups=age_groups)

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
@app.route('/packages')
def manage_packages():
    packages = EnrollmentPackage.query.all()
    age_groups = AgeGroup.query.all()
    return render_template('packages.html', packages=packages, age_groups=age_groups)

@app.route('/packages/add', methods=['POST'])
def add_package():
    data = request.form
    package = EnrollmentPackage(
        name=data['name'],
        short_code=data.get('short_code', ''),
        description=data.get('description', ''),
        age_group_id=int(data['age_group_id']) if data.get('age_group_id') else None,
        core_plan_id=int(data['core_plan_id']),
        extended_care_start_time=data.get('extended_care_start_time'),
        extended_care_end_time=data.get('extended_care_end_time'),
        monthly_tuition=float(data['monthly_tuition']),
        is_active=data.get('is_active') == 'on'
    )
    db.session.add(package)
    db.session.flush()  # Get the package ID

    # Add selected add-ons
    import json
    if data.get('addons_json'):
        addons = json.loads(data['addons_json'])
        for addon_data in addons:
            package_addon = PackageAddOn(
                package_id=package.id,
                addon_id=int(addon_data['id']),
                quantity=int(addon_data['quantity'])
            )
            db.session.add(package_addon)

    # Add selected fees
    if data.get('fees_json'):
        fees = json.loads(data['fees_json'])
        for fee_id in fees:
            package_fee = PackageFee(
                package_id=package.id,
                fee_id=int(fee_id)
            )
            db.session.add(package_fee)

    # Add selected discounts
    if data.get('discounts_json'):
        discounts = json.loads(data['discounts_json'])
        for discount_id in discounts:
            package_discount = PackageDiscount(
                package_id=package.id,
                discount_id=int(discount_id)
            )
            db.session.add(package_discount)

    db.session.commit()
    return redirect(url_for('manage_packages'))

@app.route('/packages/delete/<int:id>', methods=['POST'])
def delete_package(id):
    package = EnrollmentPackage.query.get_or_404(id)
    db.session.delete(package)
    db.session.commit()
    return redirect(url_for('manage_packages'))

@app.route('/packages/toggle/<int:id>', methods=['POST'])
def toggle_package(id):
    package = EnrollmentPackage.query.get_or_404(id)
    package.is_active = not package.is_active
    db.session.commit()
    return redirect(url_for('manage_packages'))

# Enrollment Routes
@app.route('/enrollment')
def manage_enrollment():
    enrollments = Enrollment.query.all()
    packages = EnrollmentPackage.query.filter_by(is_active=True).all()
    age_groups = AgeGroup.query.all()
    return render_template('enrollment.html', enrollments=enrollments, packages=packages, age_groups=age_groups)

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

# Schedule Routes
@app.route('/schedule')
def monthly_schedule():
    """View typical monthly schedule pattern"""

    # Create a simple 4-week calendar with just day-of-week patterns
    # Each "day" is just labeled Mon, Tue, Wed, Thu, Fri
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    # Get all active enrollments
    enrollments = Enrollment.query.filter_by(status='active').all()

    # Build schedule data for each day of the week
    schedule_data = {}
    for day_name in days_of_week:
        day_attr = day_name.lower()
        total_children = 0
        attending_enrollments = []

        for enrollment in enrollments:
            # Check if package includes this day of the week
            core_plan = enrollment.package.core_plan

            if hasattr(core_plan, day_attr) and getattr(core_plan, day_attr):
                total_children += enrollment.child_count
                attending_enrollments.append({
                    'enrollment': enrollment,
                    'count': enrollment.child_count,
                    'core_start': core_plan.start_time,
                    'core_end': core_plan.end_time,
                    'extended_start': enrollment.package.extended_care_start_time,
                    'extended_end': enrollment.package.extended_care_end_time
                })

        schedule_data[day_name] = {
            'day_name': day_name,
            'total_children': total_children,
            'enrollments': attending_enrollments
        }

    # Create a simple 4-week calendar structure for display
    calendar = []
    for week in range(4):
        calendar.append(days_of_week[:])

    return render_template('schedule_monthly.html',
                         month_name="Typical Month",
                         calendar=calendar,
                         schedule_data=schedule_data,
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
    """View detailed schedule for a specific day of the week"""
    import json

    # Validate day name
    valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    if day_name_str not in valid_days:
        return jsonify({'error': 'Invalid day name'}), 400

    # Get all active enrollments attending this day
    enrollments = Enrollment.query.filter_by(status='active').all()
    attending = []

    for enrollment in enrollments:
        core_plan = enrollment.package.core_plan
        day_attr = day_name_str.lower()

        if hasattr(core_plan, day_attr) and getattr(core_plan, day_attr):
            # Determine actual start/end times
            start_time = enrollment.package.extended_care_start_time or core_plan.start_time
            end_time = enrollment.package.extended_care_end_time or core_plan.end_time

            attending.append({
                'id': enrollment.id,
                'count': enrollment.child_count,
                'age_group': enrollment.age_group.name,
                'age_group_id': enrollment.age_group_id,
                'start_time': format_time_12hr(start_time),
                'end_time': format_time_12hr(end_time),
                'core_start': core_plan.start_time,
                'core_end': core_plan.end_time,
                'package_name': enrollment.package.short_code or enrollment.package.name
            })

    # Calculate required staffing by age group and time slot
    age_group_counts = {}
    for item in attending:
        ag_id = item['age_group_id']
        if ag_id not in age_group_counts:
            age_group = AgeGroup.query.get(ag_id)
            age_group_counts[ag_id] = {
                'name': age_group.name,
                'ratio': age_group.required_ratio,
                'count': 0,
                'required_staff': 0
            }
        age_group_counts[ag_id]['count'] += item['count']

    # Calculate required staff for each age group
    for ag_id, data in age_group_counts.items():
        age_group = AgeGroup.query.get(ag_id)
        staff, children_per_staff = age_group.get_ratio_parts()
        required = (data['count'] + children_per_staff - 1) // children_per_staff * staff
        age_group_counts[ag_id]['required_staff'] = required

    return jsonify({
        'day_name': day_name_str,
        'total_children': sum(item['count'] for item in attending),
        'children': attending,
        'age_group_breakdown': list(age_group_counts.values()),
        'total_staff_required': sum(ag['required_staff'] for ag in age_group_counts.values())
    })

@app.route('/initialize-db')
def initialize_db():
    """Initialize database with sample data"""
    import json
    db.create_all()

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

    # Add core plans if none exist
    if CorePlan.query.count() == 0:
        full_time = CorePlan(
            name='Full Time',
            description='',
            base_price=1250.0,
            billing_period='monthly',
            age_group_id=None,
            monday=True,
            tuesday=True,
            wednesday=True,
            thursday=True,
            friday=True,
            start_time='9:00 AM',
            end_time='3:00 PM',
            is_active=True
        )

        part_time = CorePlan(
            name='Part Time',
            description='',
            base_price=950.0,
            billing_period='monthly',
            age_group_id=None,
            monday=True,
            tuesday=False,
            wednesday=True,
            thursday=False,
            friday=True,
            start_time='9:00 AM',
            end_time='3:00 PM',
            is_active=True
        )

        intro = CorePlan(
            name='Intro',
            description='',
            base_price=750.0,
            billing_period='monthly',
            age_group_id=None,
            monday=False,
            tuesday=True,
            wednesday=False,
            thursday=True,
            friday=False,
            start_time='9:00 AM',
            end_time='3:00 PM',
            is_active=True
        )

        sample_plans = [full_time, part_time, intro]
        for plan in sample_plans:
            db.session.add(plan)
        db.session.commit()

    # Add add-ons if none exist
    if AddOn.query.count() == 0:
        extended_care = AddOn(
            name='Extended Care',
            description='',
            pricing_type='time_based',
            price=15.0,
            minutes_unit=60,
            is_extended_care=True,
            is_active=True
        )

        kellys_corner = AddOn(
            name="Kelly's Corner",
            description='',
            pricing_type='per_day',
            price=10.0,
            minutes_unit=1,
            is_extended_care=False,
            is_active=True
        )

        db.session.add(extended_care)
        db.session.add(kellys_corner)
        db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        initialize_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
