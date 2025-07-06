from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from models import Dormitory, Room, Bed, BedAssignment, Student, db
from utils.decorators import permission_required
from datetime import datetime, date

dormitories = Blueprint('dormitories', __name__)

@dormitories.route('/dormitories')
@login_required
@permission_required('view_students')
def dormitory_dashboard():
    """Main dormitory management dashboard"""
    try:
        # Get all dormitories with their statistics
        dormitories_list = Dormitory.query.filter_by(is_active=True).all()
        
        # Get overall statistics
        total_dormitories = len(dormitories_list)
        total_rooms = sum(dorm.total_rooms for dorm in dormitories_list)
        total_beds = sum(dorm.total_beds for dorm in dormitories_list)
        occupied_beds = sum(dorm.occupied_beds for dorm in dormitories_list)
        available_beds = total_beds - occupied_beds
        
        overall_occupancy = round((occupied_beds / total_beds) * 100, 1) if total_beds > 0 else 0
        
        return render_template('dormitory_dashboard.html',
                             dormitories=dormitories_list,
                             total_dormitories=total_dormitories,
                             total_rooms=total_rooms,
                             total_beds=total_beds,
                             occupied_beds=occupied_beds,
                             available_beds=available_beds,
                             overall_occupancy=overall_occupancy)
    
    except Exception as e:
        current_app.logger.error(f"Error loading dormitory dashboard: {str(e)}")
        flash(f'Error loading dormitory dashboard: {str(e)}', 'error')
        return redirect(url_for('core.index'))

@dormitories.route('/dormitories/map')
@login_required
@permission_required('view_students')
def dormitory_map():
    """Visual map view of all dormitories, rooms, and beds"""
    try:
        dormitories_list = Dormitory.query.filter_by(is_active=True).all()
        
        return render_template('dormitory_map.html',
                             dormitories=dormitories_list)
    
    except Exception as e:
        current_app.logger.error(f"Error loading dormitory map: {str(e)}")
        flash(f'Error loading dormitory map: {str(e)}', 'error')
        return redirect(url_for('dormitories.dormitory_dashboard'))

@dormitories.route('/api/dormitories', methods=['GET', 'POST'])
@login_required
@permission_required('edit_students')
def api_dormitories():
    """Get all dormitories or create a new one"""
    try:
        if request.method == 'GET':
            dormitories_list = Dormitory.query.all()
            return jsonify({
                'success': True,
                'dormitories': [dorm.to_dict() for dorm in dormitories_list]
            })
        
        elif request.method == 'POST':
            data = request.get_json()
            
            # Create new dormitory
            dormitory = Dormitory(
                name=data.get('name'),
                display_name=data.get('display_name'),
                description=data.get('description'),
                address=data.get('address'),
                map_color=data.get('map_color', '#3498db'),
                map_position_x=data.get('map_position_x', 0),
                map_position_y=data.get('map_position_y', 0),
                notes=data.get('notes')
            )
            
            db.session.add(dormitory)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Dormitory "{dormitory.name}" created successfully',
                'dormitory': dormitory.to_dict()
            })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error managing dormitories: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@dormitories.route('/api/dormitories/<int:dormitory_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
@permission_required('edit_students')
def api_dormitory(dormitory_id):
    """Get, update, or delete a specific dormitory"""
    try:
        dormitory = Dormitory.query.get_or_404(dormitory_id)
        
        if request.method == 'GET':
            return jsonify({
                'success': True,
                'dormitory': dormitory.to_dict()
            })
        
        elif request.method == 'PUT':
            data = request.get_json()
            
            # Update dormitory fields
            dormitory.name = data.get('name', dormitory.name)
            dormitory.display_name = data.get('display_name', dormitory.display_name)
            dormitory.description = data.get('description', dormitory.description)
            dormitory.address = data.get('address', dormitory.address)
            dormitory.map_color = data.get('map_color', dormitory.map_color)
            dormitory.map_position_x = data.get('map_position_x', dormitory.map_position_x)
            dormitory.map_position_y = data.get('map_position_y', dormitory.map_position_y)
            dormitory.is_active = data.get('is_active', dormitory.is_active)
            dormitory.allows_assignments = data.get('allows_assignments', dormitory.allows_assignments)
            dormitory.notes = data.get('notes', dormitory.notes)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Dormitory "{dormitory.name}" updated successfully',
                'dormitory': dormitory.to_dict()
            })
        
        elif request.method == 'DELETE':
            if dormitory.occupied_beds > 0:
                return jsonify({
                    'success': False,
                    'message': 'Cannot delete dormitory with occupied beds'
                }), 400
            
            name = dormitory.name
            db.session.delete(dormitory)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Dormitory "{name}" deleted successfully'
            })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error managing dormitory {dormitory_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@dormitories.route('/api/dormitories/<int:dormitory_id>/rooms', methods=['GET', 'POST'])
@login_required
@permission_required('edit_students')
def api_dormitory_rooms(dormitory_id):
    """Get rooms in a dormitory or create a new room"""
    try:
        dormitory = Dormitory.query.get_or_404(dormitory_id)
        
        if request.method == 'GET':
            rooms = dormitory.rooms.all()
            return jsonify({
                'success': True,
                'dormitory': dormitory.to_dict(),
                'rooms': [room.to_dict() for room in rooms]
            })
        
        elif request.method == 'POST':
            data = request.get_json()
            
            # Create new room
            room = Room(
                dormitory_id=dormitory_id,
                room_number=data.get('room_number'),
                room_name=data.get('room_name'),
                floor=data.get('floor'),
                room_type=data.get('room_type', 'Standard'),
                bed_count=data.get('bed_count', 2),
                has_private_bathroom=data.get('has_private_bathroom', False),
                has_air_conditioning=data.get('has_air_conditioning', True),
                has_heating=data.get('has_heating', True),
                amenities=data.get('amenities', []),
                map_position_x=data.get('map_position_x', 0),
                map_position_y=data.get('map_position_y', 0),
                notes=data.get('notes')
            )
            
            db.session.add(room)
            db.session.flush()  # Get the room ID
            
            # Create beds for the room
            room.create_beds()
            
            return jsonify({
                'success': True,
                'message': f'Room "{room.room_number}" created successfully with {room.bed_count} beds',
                'room': room.to_dict()
            })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error managing rooms for dormitory {dormitory_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@dormitories.route('/api/rooms/<int:room_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
@permission_required('edit_students')
def api_room(room_id):
    """Get, update, or delete a specific room"""
    try:
        room = Room.query.get_or_404(room_id)
        
        if request.method == 'GET':
            beds = room.beds.all()
            return jsonify({
                'success': True,
                'room': room.to_dict(),
                'beds': [bed.to_dict() for bed in beds]
            })
        
        elif request.method == 'PUT':
            data = request.get_json()
            
            # Update room fields
            room.room_number = data.get('room_number', room.room_number)
            room.room_name = data.get('room_name', room.room_name)
            room.floor = data.get('floor', room.floor)
            room.room_type = data.get('room_type', room.room_type)
            old_bed_count = room.bed_count
            room.bed_count = data.get('bed_count', room.bed_count)
            room.has_private_bathroom = data.get('has_private_bathroom', room.has_private_bathroom)
            room.has_air_conditioning = data.get('has_air_conditioning', room.has_air_conditioning)
            room.has_heating = data.get('has_heating', room.has_heating)
            room.amenities = data.get('amenities', room.amenities)
            room.map_position_x = data.get('map_position_x', room.map_position_x)
            room.map_position_y = data.get('map_position_y', room.map_position_y)
            room.is_active = data.get('is_active', room.is_active)
            room.allows_assignments = data.get('allows_assignments', room.allows_assignments)
            room.notes = data.get('notes', room.notes)
            
            # Update beds if bed count changed
            if old_bed_count != room.bed_count:
                room.create_beds()
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Room "{room.room_number}" updated successfully',
                'room': room.to_dict()
            })
        
        elif request.method == 'DELETE':
            if room.occupied_beds > 0:
                return jsonify({
                    'success': False,
                    'message': 'Cannot delete room with occupied beds'
                }), 400
            
            room_number = room.room_number
            db.session.delete(room)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Room "{room_number}" deleted successfully'
            })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error managing room {room_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@dormitories.route('/api/beds/<int:bed_id>', methods=['GET', 'PUT'])
@login_required
@permission_required('edit_students')
def api_bed(bed_id):
    """Get or update a specific bed"""
    try:
        bed = Bed.query.get_or_404(bed_id)
        
        if request.method == 'GET':
            return jsonify({
                'success': True,
                'bed': bed.to_dict()
            })
        
        elif request.method == 'PUT':
            data = request.get_json()
            
            # Update bed fields
            bed.bed_number = data.get('bed_number', bed.bed_number)
            bed.bed_type = data.get('bed_type', bed.bed_type)
            bed.is_top_bunk = data.get('is_top_bunk', bed.is_top_bunk)
            bed.is_bottom_bunk = data.get('is_bottom_bunk', bed.is_bottom_bunk)
            bed.has_desk = data.get('has_desk', bed.has_desk)
            bed.has_dresser = data.get('has_dresser', bed.has_dresser)
            bed.has_closet = data.get('has_closet', bed.has_closet)
            bed.map_position_x = data.get('map_position_x', bed.map_position_x)
            bed.map_position_y = data.get('map_position_y', bed.map_position_y)
            bed.is_active = data.get('is_active', bed.is_active)
            bed.allows_assignments = data.get('allows_assignments', bed.allows_assignments)
            bed.condition = data.get('condition', bed.condition)
            bed.notes = data.get('notes', bed.notes)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Bed "{bed.full_bed_name}" updated successfully',
                'bed': bed.to_dict()
            })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error managing bed {bed_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@dormitories.route('/api/beds/<int:bed_id>/assign', methods=['POST'])
@login_required
@permission_required('edit_students')
def assign_bed(bed_id):
    """Assign a student to a bed"""
    try:
        bed = Bed.query.get_or_404(bed_id)
        data = request.get_json()
        student_id = data.get('student_id')
        
        if not student_id:
            return jsonify({
                'success': False,
                'message': 'Student ID is required'
            }), 400
        
        # Verify student exists
        student = Student.query.get(student_id)
        if not student:
            return jsonify({
                'success': False,
                'message': 'Student not found'
            }), 404
        
        # Check if student already has an active bed assignment
        existing_assignment = BedAssignment.get_current_assignment_for_student(student_id)
        if existing_assignment:
            return jsonify({
                'success': False,
                'message': f'Student {student.student_name} already has an active bed assignment in {existing_assignment.bed.full_bed_name}'
            }), 400
        
        # Assign the bed
        start_date_str = data.get('start_date')
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today()
        
        assignment = bed.assign_student(
            student_id=student_id,
            start_date=start_date,
            assigned_by=current_user.username,
            notes=data.get('notes')
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{student.student_name} assigned to {bed.full_bed_name}',
            'assignment': assignment.to_dict()
        })
    
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error assigning bed {bed_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@dormitories.route('/api/beds/<int:bed_id>/unassign', methods=['POST'])
@login_required
@permission_required('edit_students')
def unassign_bed(bed_id):
    """Unassign the current occupant from a bed"""
    try:
        bed = Bed.query.get_or_404(bed_id)
        data = request.get_json()
        
        # Unassign current occupant
        end_date_str = data.get('end_date')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else date.today()
        
        assignment = bed.unassign_current_occupant(
            end_date=end_date,
            reason=data.get('reason', 'Manual Unassignment'),
            ended_by=current_user.username
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{assignment.student.student_name} unassigned from {bed.full_bed_name}',
            'assignment': assignment.to_dict()
        })
    
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error unassigning bed {bed_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@dormitories.route('/api/students/<student_id>/bed-assignment', methods=['GET'])
@login_required
@permission_required('view_students')
def student_bed_assignment(student_id):
    """Get current and historical bed assignments for a student"""
    try:
        student = Student.query.get_or_404(student_id)
        
        # Get current assignment
        current_assignment = BedAssignment.get_current_assignment_for_student(student_id)
        
        # Get assignment history
        assignment_history = BedAssignment.get_assignment_history_for_student(student_id)
        
        return jsonify({
            'success': True,
            'student': {
                'id': student.id,
                'name': student.student_name,
                'division': student.division
            },
            'current_assignment': current_assignment.to_dict() if current_assignment else None,
            'assignment_history': [assignment.to_dict() for assignment in assignment_history]
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting bed assignment for student {student_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@dormitories.route('/api/dormitories/statistics', methods=['GET'])
@login_required
@permission_required('view_students')
def dormitory_statistics():
    """Get overall dormitory system statistics"""
    try:
        # Get all dormitories
        dormitories_list = Dormitory.query.filter_by(is_active=True).all()
        
        # Calculate statistics
        stats = {
            'overview': {
                'total_dormitories': len(dormitories_list),
                'total_rooms': sum(dorm.total_rooms for dorm in dormitories_list),
                'total_beds': sum(dorm.total_beds for dorm in dormitories_list),
                'occupied_beds': sum(dorm.occupied_beds for dorm in dormitories_list),
                'available_beds': sum(dorm.available_beds for dorm in dormitories_list)
            },
            'dormitories': [dorm.to_dict() for dorm in dormitories_list]
        }
        
        # Calculate overall occupancy rate
        if stats['overview']['total_beds'] > 0:
            stats['overview']['occupancy_rate'] = round(
                (stats['overview']['occupied_beds'] / stats['overview']['total_beds']) * 100, 1
            )
        else:
            stats['overview']['occupancy_rate'] = 0
        
        # Get assignments by division
        active_assignments = db.session.query(BedAssignment, Student).join(
            Student, BedAssignment.student_id == Student.id
        ).filter(BedAssignment.is_active == True).all()
        
        division_stats = {}
        for assignment, student in active_assignments:
            division = student.division
            if division not in division_stats:
                division_stats[division] = 0
            division_stats[division] += 1
        
        stats['by_division'] = division_stats
        
        return jsonify({
            'success': True,
            'statistics': stats
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting dormitory statistics: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@dormitories.route('/api/students/available-for-assignment', methods=['GET'])
@login_required
@permission_required('view_students')
def students_available_for_assignment():
    """Get list of students who don't have active bed assignments"""
    try:
        # Get all active students
        all_students = Student.query.filter_by(status='Active').all()
        
        # Get students with active assignments
        students_with_assignments = db.session.query(Student).join(
            BedAssignment, Student.id == BedAssignment.student_id
        ).filter(BedAssignment.is_active == True).all()
        
        assigned_student_ids = {student.id for student in students_with_assignments}
        
        # Filter out students who already have assignments
        available_students = [
            {
                'id': student.id,
                'name': student.student_name,
                'division': student.division,
                'email': student.email
            }
            for student in all_students 
            if student.id not in assigned_student_ids
        ]
        
        return jsonify({
            'success': True,
            'available_students': available_students,
            'count': len(available_students)
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting available students: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@dormitories.route('/api/beds/unassigned', methods=['GET'])
@login_required
@permission_required('view_students')
def get_unassigned_beds():
    """Get list of beds that are available for assignment"""
    try:
        # Get all beds that are not currently assigned
        unassigned_beds = db.session.query(Bed, Room, Dormitory).join(
            Room, Bed.room_id == Room.id
        ).join(
            Dormitory, Room.dormitory_id == Dormitory.id
        ).outerjoin(
            BedAssignment, (Bed.id == BedAssignment.bed_id) & (BedAssignment.is_active == True)
        ).filter(
            BedAssignment.id.is_(None),  # No active assignment
            Bed.is_active == True,
            Bed.allows_assignments == True,
            Bed.condition.in_(['Good', 'Fair']),  # Exclude beds needing repair or out of order
            Room.is_active == True,
            Room.allows_assignments == True,
            Dormitory.is_active == True,
            Dormitory.allows_assignments == True
        ).all()
        
        # Format the data for response
        beds_data = []
        for bed, room, dormitory in unassigned_beds:
            beds_data.append({
                'bed_id': bed.id,
                'bed_number': bed.bed_number,
                'bed_type': bed.bed_type,
                'full_bed_name': bed.full_bed_name,
                'room_id': room.id,
                'room_number': room.room_number,
                'room_name': room.room_name,
                'dormitory_id': dormitory.id,
                'dormitory_name': dormitory.name,
                'dormitory_color': dormitory.map_color,
                'condition': bed.condition,
                'has_desk': bed.has_desk,
                'has_dresser': bed.has_dresser,
                'has_closet': bed.has_closet,
                'room_amenities': {
                    'has_private_bathroom': room.has_private_bathroom,
                    'has_air_conditioning': room.has_air_conditioning,
                    'has_heating': room.has_heating,
                    'amenities': room.amenities or []
                }
            })
        
        return jsonify({
            'success': True,
            'unassigned_beds': beds_data,
            'count': len(beds_data)
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting unassigned beds: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@dormitories.route('/api/students/dormitory-without-beds', methods=['GET'])
@login_required
@permission_required('view_students')
def get_dormitory_students_without_beds():
    """Get dormitory students who don't have bed assignments"""
    try:
        # Get all active students who should have dormitory beds but don't
        # This includes students who have dormitory_meals_option indicating they need housing
        
        # First, get all students with active bed assignments
        students_with_beds = db.session.query(Student).join(
            BedAssignment, Student.id == BedAssignment.student_id
        ).filter(BedAssignment.is_active == True).all()
        
        assigned_student_ids = {student.id for student in students_with_beds}
        
        # Get students who should have beds but don't
        # Students who need dormitory housing based on their dormitory_meals_option
        dormitory_students_without_beds = Student.query.filter(
            Student.status == 'Active',
            Student.id.notin_(assigned_student_ids),
            Student.dormitory_meals_option.isnot(None),  # Has some dormitory/meals selection
            Student.dormitory_meals_option != '',  # Not empty
            Student.dormitory_meals_option.like('%dorm%')  # Contains "dorm" indicating dormitory housing
        ).all()
        
        # Also include students explicitly marked as needing housing (you can customize this logic)
        additional_students = Student.query.filter(
            Student.status == 'Active',
            Student.id.notin_(assigned_student_ids),
            # Add additional criteria based on your institution's needs
            # For example, you might have a custom field indicating housing needs
        ).all()
        
        # Combine and remove duplicates
        all_students_needing_beds = list(set(dormitory_students_without_beds + additional_students))
        
        # Format the data
        students_data = []
        for student in all_students_needing_beds:
            students_data.append({
                'id': student.id,
                'name': student.student_name,
                'division': student.division,
                'email': student.email,
                'phone_number': student.phone_number,
                'dormitory_meals_option': student.dormitory_meals_option,
                'date_of_birth': student.date_of_birth.isoformat() if student.date_of_birth else None,
                'accepted_date': student.accepted_date.isoformat() if student.accepted_date else None,
                'status': student.status
            })
        
        return jsonify({
            'success': True,
            'students_without_beds': students_data,
            'count': len(students_data)
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting dormitory students without beds: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500 