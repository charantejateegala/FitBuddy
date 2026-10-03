from datetime import datetime
import os
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'fitbuddy-fitness-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fitbuddy.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth'
login_manager.login_message_category = 'warning'

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    city = db.Column(db.String(80), default="Hyderabad")
    activity = db.Column(db.String(50), default="Gym")
    level = db.Column(db.String(50), default="Intermediate")
    workout_time = db.Column(db.String(50), default="Morning (06:00 - 08:00 AM)")
    bio = db.Column(db.Text, default="Committed to fitness and strength training.")

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    activity = db.Column(db.String(50), nullable=False)
    date_time = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    target_weight = db.Column(db.Float, nullable=True)
    bar_weight = db.Column(db.Float, nullable=True, default=20.0)
    unit = db.Column(db.String(10), default='kg')
    plates_breakdown = db.Column(db.String(255), nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    creator = db.relationship('User', backref=db.backref('created_sessions', lazy=True))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, nullable=False)
    reported_user_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# --- GYM TRACKER & PROGRESSIVE OVERLOAD MODELS ---
class Exercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(50), default="Compound")
    equipment = db.Column(db.String(50), default="Barbell")
    description = db.Column(db.Text, nullable=True)
    default_bar_weight = db.Column(db.Float, default=20.0)

    set_logs = db.relationship('SetLog', backref='exercise', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'equipment': self.equipment,
            'description': self.description,
            'default_bar_weight': self.default_bar_weight
        }

class WorkoutSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(120), nullable=False, default="Gym Workout")
    date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    social_session_id = db.Column(db.Integer, db.ForeignKey('session.id'), nullable=True)

    user = db.relationship('User', backref=db.backref('workout_logs', lazy=True))
    social_session = db.relationship('Session', backref=db.backref('linked_workout_session', uselist=False))
    sets = db.relationship('SetLog', backref='workout_session', lazy=True, cascade='all, delete-orphan', order_by='SetLog.set_number')

    @property
    def total_volume(self):
        """Calculates total tonnage/volume moved in the workout session."""
        return sum(s.volume for s in self.sets if s.completed)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'date': self.date.strftime('%Y-%m-%d %H:%M') if self.date else None,
            'notes': self.notes,
            'duration_minutes': self.duration_minutes,
            'total_volume': self.total_volume,
            'sets_count': len(self.sets)
        }

class SetLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workout_session_id = db.Column(db.Integer, db.ForeignKey('workout_session.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercise.id'), nullable=False)
    set_number = db.Column(db.Integer, nullable=False, default=1)
    
    # Progressive Overload Core Fields
    weight = db.Column(db.Float, nullable=False)           # Actual load lifted
    reps = db.Column(db.Integer, nullable=False)            # Repetitions performed
    target_weight = db.Column(db.Float, nullable=True)     # Planned progressive overload weight
    target_reps = db.Column(db.Integer, nullable=True)     # Planned progressive overload reps
    rpe = db.Column(db.Float, nullable=True)               # Rate of Perceived Exertion (1.0 - 10.0)
    reps_in_reserve = db.Column(db.Integer, nullable=True) # Reps in Reserve (RIR)
    unit = db.Column(db.String(10), default='kg')          # 'kg' or 'lbs'
    
    # Overload Progress Metrics
    is_pr = db.Column(db.Boolean, default=False)           # Personal Record milestone flag
    weight_increase = db.Column(db.Float, default=0.0)     # Progressive weight delta over prior benchmark
    plates_breakdown = db.Column(db.String(255), nullable=True) # Olympic plates breakdown
    notes = db.Column(db.String(255), nullable=True)       # Overload cue notes
    completed = db.Column(db.Boolean, default=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def volume(self):
        """Calculates workload volume for progressive volume overload tracking."""
        return round((self.weight or 0.0) * (self.reps or 0), 2)

    def to_dict(self):
        return {
            'id': self.id,
            'workout_session_id': self.workout_session_id,
            'exercise_id': self.exercise_id,
            'exercise_name': self.exercise.name if self.exercise else None,
            'set_number': self.set_number,
            'weight': self.weight,
            'reps': self.reps,
            'target_weight': self.target_weight,
            'target_reps': self.target_reps,
            'rpe': self.rpe,
            'reps_in_reserve': self.reps_in_reserve,
            'unit': self.unit,
            'volume': self.volume,
            'is_pr': self.is_pr,
            'weight_increase': self.weight_increase,
            'plates_breakdown': self.plates_breakdown,
            'notes': self.notes,
            'completed': self.completed
        }

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- MATCHING CALCULATION ---
def calculate_compatibility(u1, u2):
    score = 40
    if u1.activity == u2.activity:
        score += 30
    if u1.level == u2.level:
        score += 15
    if u1.city.strip().lower() == u2.city.strip().lower():
        score += 15
    return min(score, 100)

# --- PLATE-MATH CALCULATOR HELPER ---
def calculate_plate_math(target_weight, bar_weight=20.0, unit='kg', available_plates=None):
    """
    Calculates the exact plate distribution per side for a given target barbell weight.
    Supports both metric (kg) and imperial (lbs) with customizable plate inventory.
    """
    try:
        target = float(target_weight)
        bar = float(bar_weight) if bar_weight is not None else (20.0 if unit == 'kg' else 45.0)
    except (ValueError, TypeError):
        return {'error': 'Invalid weight format'}

    if target < bar:
        return {
            'target': target,
            'bar': bar,
            'unit': unit,
            'per_side': 0.0,
            'breakdown': {},
            'summary': f'Bar only (Target is less than bar weight of {bar} {unit})',
            'achievable': bar,
            'remainder': 0.0
        }

    rem_per_side = (target - bar) / 2.0

    if available_plates:
        try:
            denoms = sorted([float(p) for p in available_plates if float(p) > 0], reverse=True)
        except (ValueError, TypeError):
            denoms = [25.0, 20.0, 15.0, 10.0, 5.0, 2.5, 1.25] if unit == 'kg' else [45.0, 35.0, 25.0, 10.0, 5.0, 2.5]
    else:
        denoms = [25.0, 20.0, 15.0, 10.0, 5.0, 2.5, 1.25] if unit == 'kg' else [45.0, 35.0, 25.0, 10.0, 5.0, 2.5]

    breakdown = {}
    rem = round(rem_per_side, 3)
    for p in denoms:
        cnt = int(rem // p)
        if cnt > 0:
            formatted_p = int(p) if p.is_integer() else p
            breakdown[formatted_p] = cnt
            rem = round(rem - (cnt * p), 3)

    summary_parts = [f"{cnt} × {p} {unit}" for p, cnt in breakdown.items()]
    summary = ", ".join(summary_parts) if summary_parts else f"Bar only (0 {unit} / side)"
    achieved_weight = round(bar + ((rem_per_side - rem) * 2), 2)
    formatted_achieved = int(achieved_weight) if achieved_weight.is_integer() else achieved_weight

    return {
        'target': target,
        'bar': bar,
        'unit': unit,
        'per_side': round(rem_per_side, 2),
        'breakdown': breakdown,
        'summary': f"{summary} per side" if summary_parts else summary,
        'achievable': formatted_achieved,
        'remainder': round(rem * 2, 2)
    }

# --- ROUTES ---
@app.route('/')
def landing():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if action == 'register':
            name = request.form.get('name', '').strip()
            city = request.form.get('city', 'Hyderabad')
            activity = request.form.get('activity', 'Gym')
            level = request.form.get('level', 'Intermediate')

            if User.query.filter_by(email=email).first():
                flash('An account with this email already exists.', 'danger')
                return redirect(url_for('auth'))

            new_user = User(
                name=name,
                email=email,
                password_hash=generate_password_hash(password),
                city=city,
                activity=activity,
                level=level
            )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            flash('Welcome to FitBuddy!', 'success')
            return redirect(url_for('dashboard'))

        elif action == 'login':
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                flash('Logged in successfully.', 'success')
                return redirect(url_for('dashboard'))
            flash('Invalid email or password credentials.', 'danger')

    return render_template('auth.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have logged out.', 'info')
    return redirect(url_for('landing'))

@app.route('/dashboard')
@login_required
def dashboard():
    potential_buddies = User.query.filter(User.id != current_user.id).limit(3).all()
    partners = []
    for buddy in potential_buddies:
        partners.append({
            'user': buddy,
            'match_score': calculate_compatibility(current_user, buddy)
        })
    recent_sessions = Session.query.order_by(Session.id.desc()).limit(3).all()
    return render_template('dashboard.html', partners=partners, sessions=recent_sessions)

@app.route('/discover')
@login_required
def discover():
    activity_filter = request.args.get('activity')
    query = User.query.filter(User.id != current_user.id)
    if activity_filter:
        query = query.filter_by(activity=activity_filter)
    
    users = query.all()
    buddies = []
    for u in users:
        buddies.append({
            'user': u,
            'match_score': calculate_compatibility(current_user, u)
        })
    buddies = sorted(buddies, key=lambda x: x['match_score'], reverse=True)
    return render_template('discover.html', buddies=buddies, selected_activity=activity_filter)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        current_user.city = request.form.get('city')
        current_user.activity = request.form.get('activity')
        current_user.level = request.form.get('level')
        current_user.workout_time = request.form.get('workout_time')
        current_user.bio = request.form.get('bio')
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    return render_template('profile.html')

@app.route('/sessions', methods=['GET', 'POST'])
@login_required
def sessions():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        activity = request.form.get('activity', 'Gym')
        date_time = request.form.get('date_time', '').strip()
        location = request.form.get('location', '').strip()
        
        target_weight_raw = request.form.get('target_weight')
        target_weight = float(target_weight_raw) if target_weight_raw and target_weight_raw.strip() else None
        bar_weight_raw = request.form.get('bar_weight')
        bar_weight = float(bar_weight_raw) if bar_weight_raw and bar_weight_raw.strip() else 20.0
        unit = request.form.get('unit', 'kg').strip().lower()
        plates_breakdown = request.form.get('plates_breakdown', '').strip()

        # If it's a Gym session and target weight was specified, calculate or verify plate breakdown
        if activity == 'Gym' and target_weight:
            calc_result = calculate_plate_math(target_weight, bar_weight, unit)
            if not plates_breakdown:
                plates_breakdown = calc_result.get('summary', '')

        new_session = Session(
            title=title,
            activity=activity,
            date_time=date_time,
            location=location,
            creator_id=current_user.id,
            target_weight=target_weight if (activity == 'Gym' and target_weight) else None,
            bar_weight=bar_weight if (activity == 'Gym' and target_weight) else None,
            unit=unit if (activity == 'Gym' and target_weight) else 'kg',
            plates_breakdown=plates_breakdown if (activity == 'Gym' and target_weight) else None
        )
        db.session.add(new_session)
        db.session.commit()
        flash('Workout session created!', 'success')
        return redirect(url_for('sessions'))

    all_sessions = Session.query.order_by(Session.id.desc()).all()
    return render_template('sessions.html', sessions=all_sessions)

@app.route('/tracker', methods=['GET', 'POST'])
@login_required
def tracker():
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        title = data.get('title', 'Strength Workout Session')
        notes = data.get('notes', '')
        duration = data.get('duration_minutes', 45)
        sets_data = data.get('sets', [])

        try:
            duration_val = int(duration) if duration else None
        except (ValueError, TypeError):
            duration_val = None

        workout = WorkoutSession(
            user_id=current_user.id,
            title=title,
            notes=notes,
            duration_minutes=duration_val
        )
        db.session.add(workout)
        db.session.flush()

        if isinstance(sets_data, list):
            for s in sets_data:
                exercise_id = s.get('exercise_id')
                if not exercise_id:
                    ex_name = s.get('exercise_name', 'Barbell Bench Press').strip()
                    ex = Exercise.query.filter_by(name=ex_name).first()
                    if not ex:
                        ex = Exercise(name=ex_name)
                        db.session.add(ex)
                        db.session.flush()
                    exercise_id = ex.id

                try:
                    weight_val = float(s.get('weight', 0))
                except (ValueError, TypeError):
                    weight_val = 0.0

                try:
                    reps_val = int(s.get('reps', 0))
                except (ValueError, TypeError):
                    reps_val = 0

                try:
                    rpe_val = float(s.get('rpe')) if s.get('rpe') else None
                except (ValueError, TypeError):
                    rpe_val = None

                try:
                    target_w = float(s.get('target_weight')) if s.get('target_weight') else None
                except (ValueError, TypeError):
                    target_w = None

                try:
                    target_r = int(s.get('target_reps')) if s.get('target_reps') else None
                except (ValueError, TypeError):
                    target_r = None

                try:
                    wt_inc = float(s.get('weight_increase', 0))
                except (ValueError, TypeError):
                    wt_inc = 0.0

                set_log = SetLog(
                    workout_session_id=workout.id,
                    exercise_id=int(exercise_id),
                    set_number=int(s.get('set_number', 1)),
                    weight=weight_val,
                    reps=reps_val,
                    target_weight=target_w,
                    target_reps=target_r,
                    rpe=rpe_val,
                    unit=s.get('unit', 'kg'),
                    is_pr=bool(s.get('is_pr', False)),
                    weight_increase=wt_inc,
                    plates_breakdown=s.get('plates_breakdown', ''),
                    notes=s.get('notes', ''),
                    completed=bool(s.get('completed', True))
                )
                db.session.add(set_log)

        db.session.commit()

        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': 'Workout session logged with progressive overload!',
                'workout_id': workout.id,
                'total_volume': workout.total_volume,
                'sets_count': len(workout.sets)
            })

        flash('Workout logged successfully!', 'success')
        return redirect(url_for('tracker'))

    exercises = Exercise.query.order_by(Exercise.category, Exercise.name).all()
    user_workouts = WorkoutSession.query.filter_by(user_id=current_user.id).order_by(WorkoutSession.date.desc()).limit(6).all()
    return render_template('workout_tracker.html', exercises=exercises, workouts=user_workouts)

@app.route('/api/plate-calculator', methods=['GET', 'POST'])
@app.route('/api/calculate-plates', methods=['GET', 'POST'])
def api_plate_calculator():
    """
    API endpoint to calculate Olympic barbell plate distribution for a target weight.
    Accepts target_weight, bar_weight (default 20kg/45lbs), unit ('kg' or 'lbs'), and available plates.
    """
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
    else:
        data = request.args

    raw_target = data.get('target_weight')
    if raw_target is None or str(raw_target).strip() == '':
        return jsonify({
            'success': False,
            'error': 'Missing required parameter: target_weight'
        }), 400

    try:
        target_weight = float(raw_target)
    except (ValueError, TypeError):
        return jsonify({
            'success': False,
            'error': f'Invalid target_weight value: {raw_target}'
        }), 400

    unit = str(data.get('unit', 'kg')).strip().lower()
    if unit not in ['kg', 'lbs']:
        unit = 'kg'

    default_bar = 20.0 if unit == 'kg' else 45.0
    try:
        bar_weight = float(data.get('bar_weight', default_bar))
    except (ValueError, TypeError):
        bar_weight = default_bar

    available = None
    if 'available_plates' in data or 'plates' in data:
        raw_plates = data.get('available_plates') or data.get('plates')
        if hasattr(data, 'getlist') and not isinstance(raw_plates, list):
            raw_plates = data.getlist('available_plates') or data.getlist('plates')
        if isinstance(raw_plates, str):
            raw_plates = [p.strip() for p in raw_plates.split(',') if p.strip()]
        try:
            available = [float(p) for p in raw_plates if p]
        except (ValueError, TypeError):
            available = None

    result = calculate_plate_math(target_weight, bar_weight, unit, available)

    # Olympic plate color coding mapping
    color_map_kg = {25.0: "red", 20.0: "blue", 15.0: "yellow", 10.0: "green", 5.0: "white", 2.5: "black", 1.25: "chrome"}
    color_map_lbs = {45.0: "blue", 35.0: "yellow", 25.0: "green", 10.0: "black", 5.0: "white", 2.5: "chrome"}
    color_map = color_map_kg if unit == 'kg' else color_map_lbs

    olympic_plates = []
    for p, cnt in result.get('breakdown', {}).items():
        olympic_plates.append({
            'weight': float(p),
            'count_per_side': cnt,
            'total_count': cnt * 2,
            'color': color_map.get(float(p), "standard")
        })

    return jsonify({
        'success': 'error' not in result,
        'target_weight': result.get('target', target_weight),
        'bar_weight': result.get('bar', bar_weight),
        'unit': unit,
        'weight_per_side': result.get('per_side', 0.0),
        'plates_per_side': result.get('breakdown', {}),
        'plate_summary': result.get('summary', ''),
        'achievable_weight': result.get('achievable', target_weight),
        'remainder': result.get('remainder', 0.0),
        'olympic_plates': olympic_plates
    })

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    partner_id = request.args.get('user_id', type=int)
    partner = db.session.get(User, partner_id) if partner_id else None

    if request.method == 'POST':
        receiver_id = request.form.get('receiver_id', type=int)
        message_body = request.form.get('body', '').strip()
        if receiver_id and message_body:
            msg = Message(sender_id=current_user.id, receiver_id=receiver_id, body=message_body)
            db.session.add(msg)
            db.session.commit()
            return redirect(url_for('chat', user_id=receiver_id))

    messages = []
    if partner:
        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == partner.id)) |
            ((Message.sender_id == partner.id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.timestamp.asc()).all()

    recent_users = User.query.filter(User.id != current_user.id).all()
    return render_template('chat.html', partner=partner, messages=messages, partners=recent_users)

@app.route('/safety', methods=['GET', 'POST'])
@login_required
def safety():
    if request.method == 'POST':
        reported_id = request.form.get('user_id', type=int)
        reason = request.form.get('reason', '').strip()
        if reported_id and reason:
            report = Report(reporter_id=current_user.id, reported_user_id=reported_id, reason=reason)
            db.session.add(report)
            db.session.commit()
            flash('Incident report logged. Our team prioritizes member safety.', 'info')
            return redirect(url_for('safety'))
    users = User.query.filter(User.id != current_user.id).all()
    return render_template('safety.html', users=users)

# --- DATABASE SEEDING (CHIRANJEEVI DEMO ACCOUNT) ---
def seed_demo_data():
    if not User.query.filter_by(email="chiranjeevi@example.com").first():
        demo_user = User(
            name="Chiranjeevi",
            email="chiranjeevi@example.com",
            password_hash=generate_password_hash("demo1234"),
            city="Hyderabad",
            activity="Gym",
            level="Advanced",
            workout_time="06:00 - 07:30 AM",
            bio="Passionate powerlifter and strength athlete. Looking for dedicated partners for morning lifting sessions."
        )
        partner_1 = User(
            name="Vikram Rao",
            email="vikram@example.com",
            password_hash=generate_password_hash("demo1234"),
            city="Hyderabad",
            activity="Gym",
            level="Advanced",
            workout_time="06:00 - 07:30 AM",
            bio="Hypertrophy and compound lifting specialist."
        )
        partner_2 = User(
            name="Ananya Sharma",
            email="ananya@example.com",
            password_hash=generate_password_hash("demo1234"),
            city="Hyderabad",
            activity="Running",
            level="Intermediate",
            workout_time="05:30 - 06:30 AM",
            bio="Marathon runner preparing for the upcoming half-marathon."
        )
        partner_3 = User(
            name="Rahul Verma",
            email="rahul@example.com",
            password_hash=generate_password_hash("demo1234"),
            city="Bengaluru",
            activity="Yoga",
            level="Beginner",
            workout_time="07:00 - 08:00 AM",
            bio="Focused on flexibility, recovery, and core stability."
        )
        db.session.add_all([demo_user, partner_1, partner_2, partner_3])
        db.session.commit()

        sample_session = Session(
            title="Heavy Leg Day & Deadlifts",
            activity="Gym",
            date_time="Tomorrow at 06:30 AM",
            location="Cult Fit, Jubilee Hills, Hyderabad",
            creator_id=demo_user.id,
            target_weight=140.0,
            bar_weight=20.0,
            unit="kg",
            plates_breakdown="2 × 25 kg, 1 × 10 kg per side"
        )
        sample_msg = Message(
            sender_id=partner_1.id,
            receiver_id=demo_user.id,
            body="Hey Chiranjeevi, ready for tomorrow's deadlift session?"
        )
        db.session.add_all([sample_session, sample_msg])
        db.session.commit()

    # Seed standard compound exercises & sample progressive overload workout session if not present
    if not Exercise.query.first():
        ex1 = Exercise(name="Barbell Bench Press", category="Chest", equipment="Barbell", default_bar_weight=20.0, description="Compound upper body horizontal press.")
        ex2 = Exercise(name="Barbell Back Squat", category="Legs", equipment="Barbell", default_bar_weight=20.0, description="Compound lower body bilateral squat.")
        ex3 = Exercise(name="Conventional Deadlift", category="Back", equipment="Barbell", default_bar_weight=20.0, description="Full body posterior chain pulling movement.")
        ex4 = Exercise(name="Overhead Press (OHP)", category="Shoulders", equipment="Barbell", default_bar_weight=20.0, description="Vertical barbell pressing movement for shoulders and triceps.")
        ex5 = Exercise(name="Barbell Bent-Over Row", category="Back", equipment="Barbell", default_bar_weight=20.0, description="Compound upper back horizontal pull.")
        db.session.add_all([ex1, ex2, ex3, ex4, ex5])
        db.session.commit()

        chiranjeevi = User.query.filter_by(email="chiranjeevi@example.com").first()
        if chiranjeevi:
            demo_workout = WorkoutSession(
                user_id=chiranjeevi.id,
                title="Push Day - Progressive Overload",
                notes="Hypertrophy block: Focused on +2.5kg progressive overload on bench press.",
                duration_minutes=60
            )
            db.session.add(demo_workout)
            db.session.commit()

            set1 = SetLog(
                workout_session_id=demo_workout.id,
                exercise_id=ex1.id,
                set_number=1,
                weight=100.0,
                reps=5,
                target_weight=100.0,
                target_reps=5,
                rpe=7.5,
                reps_in_reserve=2,
                unit="kg",
                is_pr=False,
                weight_increase=0.0,
                plates_breakdown="2 × 20 kg per side",
                notes="Base working set, explosive press"
            )
            set2 = SetLog(
                workout_session_id=demo_workout.id,
                exercise_id=ex1.id,
                set_number=2,
                weight=102.5,
                reps=5,
                target_weight=102.5,
                target_reps=5,
                rpe=8.5,
                reps_in_reserve=1,
                unit="kg",
                is_pr=True,
                weight_increase=2.5,
                plates_breakdown="2 × 20 kg, 1 × 1.25 kg per side",
                notes="+2.5kg PR over last session, solid bar path"
            )
            set3 = SetLog(
                workout_session_id=demo_workout.id,
                exercise_id=ex1.id,
                set_number=3,
                weight=102.5,
                reps=4,
                target_weight=102.5,
                target_reps=5,
                rpe=9.5,
                reps_in_reserve=0,
                unit="kg",
                is_pr=False,
                weight_increase=2.5,
                plates_breakdown="2 × 20 kg, 1 × 1.25 kg per side",
                notes="1 rep shy of cap, high intensity"
            )
            db.session.add_all([set1, set2, set3])
            db.session.commit()

def check_and_migrate_db():
    import sqlite3
    db_path = os.path.join(app.instance_path, 'fitbuddy.db')
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cols = [c[1] for c in cur.execute("PRAGMA table_info(session)").fetchall()]
        additions = [
            ('target_weight', 'REAL'),
            ('bar_weight', 'REAL DEFAULT 20.0'),
            ('unit', "VARCHAR(10) DEFAULT 'kg'"),
            ('plates_breakdown', 'VARCHAR(255)')
        ]
        for col, col_type in additions:
            if col not in cols:
                cur.execute(f"ALTER TABLE session ADD COLUMN {col} {col_type}")
        conn.commit()
        conn.close()

if __name__ == '__main__':
    with app.app_context():
        check_and_migrate_db()
        db.create_all()
        seed_demo_data()
    app.run(debug=True, port=5000)