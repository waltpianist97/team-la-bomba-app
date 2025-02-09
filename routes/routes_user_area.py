from app import app, db, strava_client
from flask import request, render_template, flash, redirect, url_for, session
from flask_login import current_user, login_required
from sqlalchemy import or_, and_, desc, func
from models import User, Trip, Team, TeamUserAssociation, RequestsToJoinTeam
from forms import *
from werkzeug.urls import url_parse
from datetime import datetime
from tools import send_email_utility, AUTO_MAIL, PictureUploader, stravaio
from stravaio import StravaIO
import os
from pathlib import Path
import os
import warnings


@app.route('/user_home/<username>', methods=['GET', 'POST'])
@login_required
def user_home(username):

    user = User.query.filter_by(username=current_user.username).first()
    # trips = Trip.query.filter_by(user_id=current_user.id).all()
    teams = Team.query.all()
    message = ""
    """if user_teams:
        if user in team.users and RequestsToJoinTeam.query.filter_by(team_id = team.id).all():
            message = "You have some pending enrollment requests, check out the team page!"
    """
    last_trips = Trip.query.order_by(desc(Trip.recorded_on)).filter_by(
        user_id=user.id).limit(3).all()

    if last_trips is None:
        last_trips = []
    if teams is None:
        teams = []
    stat = {}
    stat["average_speed"] = db.session.query(Trip, func.avg(Trip.speed)).group_by(
        Trip.user_id).filter_by(user_id=user.id).all()
    if stat["average_speed"]:
        stat["average_speed"] = round(stat["average_speed"][0][1], 2)
    stat["maximum_elevation"] = db.session.query(Trip, func.max(
        Trip.elevation)).group_by(Trip.user_id).filter_by(user_id=user.id).all()
    if stat["maximum_elevation"]:
        stat["maximum_elevation"] = stat["maximum_elevation"][0][1]
    stat["total_distance"] = db.session.query(Trip, func.sum(
        Trip.distance)).group_by(Trip.user_id).filter_by(user_id=user.id).all()
    if stat["total_distance"]:
        stat["total_distance"] = round(stat["total_distance"][0][1], 2)
    stat["activities"] = len(Trip.query.filter_by(user_id=user.id).all())

    return render_template('user_home.html', user=user, teams=teams, new_enrollments=message, last_trips=last_trips, stat=stat)


@app.route('/delete_file/<target>/<file_db_column>/<path:filepath>', methods=['GET', 'POST'])
@app.route('/delete_file/<target>/<file_db_column>/<path:filepath>/<int:team_id>', methods=['GET', 'POST'])
@login_required
def delete_file(target, file_db_column, filepath, team_id=None):

    picture_uploader = None

    if not team_id:
        picture_uploader = PictureUploader(target, current_user.username)
        picture_uploader.delete_file(filepath)
        if hasattr(current_user, file_db_column):
            setattr(current_user, file_db_column, None)
            db.session.commit()
        return redirect(url_for('user_profile'))

    else:
        team = Team.query.get(team_id)
        picture_uploader = PictureUploader(target, team.name)
        picture_uploader.delete_file(filepath)
        if hasattr(team, file_db_column):
            setattr(team, file_db_column, None)
            db.session.commit()
        return redirect(url_for('team_profile', team_id=team_id))


@app.route('/user_profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    user = User.query.get(current_user.id)
    form = ProfileForm(obj=user)
    teams = Team.query.all()
    picture_uploader = PictureUploader("users", current_user.username)
    is_strava_client_in_synch = False

    strava_token = session.get('strava_token', None)
    if strava_token:
        strava_client = StravaIO(access_token=strava_token)
        is_strava_client_in_synch = True
        user_from_strava = strava_client.get_logged_in_athlete().api_response
        if not user.name:
            form.name.data = user_from_strava.firstname
        if not user.surname:
            form.surname.data = user_from_strava.lastname

    if form.validate_on_submit():
        # Handle profile picture upload
        user.username = form.username.data
        user.name = form.name.data
        user.surname = form.surname.data
        user.email = form.email.data
        user.strava_account = form.strava_account.data
        user.phone_number = form.phone_number.data

        if form.profile_picture.data:
            file = form.profile_picture.data
            picture_uploader.delete_file(user.profile_picture)
            filename = picture_uploader.load_file(file)
            user.profile_picture = f'users/{current_user.username}/{filename}'

        if form.profile_background.data:
            file = form.profile_background.data
            picture_uploader.delete_file(user.profile_background)
            filename = picture_uploader.load_file(file)
            user.profile_background = f'users/{current_user.username}/{filename}'

        if form.profile_banner.data:
            file = form.profile_banner.data
            picture_uploader.delete_file(user.profile_banner)
            filename = picture_uploader.load_file(file)
            user.profile_banner = f'users/{current_user.username}/{filename}'

        db.session.commit()
        flash("Il tuo profilo e' stato aggiornato!", 'success')
        return redirect(url_for('user_profile'))
    return render_template('user_profile.html', form=form, teams=teams, is_strava_in_synch=is_strava_client_in_synch)


@app.route('/trips_overview/<int:user_id>', methods=['GET', 'POST'])
@login_required
def trips_overview(user_id):

    user = User.query.filter_by(id=user_id).first()
    result = user.group_user_trips_by_team()
    teams = Team.query.all()

    return render_template('trips_overview.html', user=user, trips_groups=result, teams=teams)


@app.route('/unenroll_from_team/<int:team_id>/<int:user_id>', methods=['GET', 'POST'])
@login_required
def unenroll_from_team(team_id, user_id):

    team = Team.query.get(team_id)
    user = User.query.get(user_id)
    trips = Trip.query.filter_by(team_id=team_id, user_id=user_id).all()

    if current_user in team.users or user in team.users:
        [db.session.delete(trip) for trip in trips]
        team.users.remove(user)
        db.session.commit()

        send_email_utility("Deregistrazione dal team",
                           f"Sei stato deregistrato dal team {team.name}!", AUTO_MAIL, user.email)
    if current_user._is_admin:
        return redirect(url_for("view_user_profile_by_admin", user_id=user.id))
    else:
        if current_user == user:
            return redirect(url_for("team_home", team_id=team_id))
        else:
            return redirect(url_for("manage_team", team_id=team_id))


@app.route('/request_enrollment_to_team/<int:team_id>', methods=['GET', 'POST'])
@login_required
def request_enrollment_to_team(team_id):

    team = Team.query.get(team_id)
    user_req = RequestsToJoinTeam.query.filter_by(
        team_id=team_id, user_id=current_user.id).first()
    if user_req:
        return redirect(url_for("team_home", team_id=team_id))

    req = RequestsToJoinTeam(team_id=team_id, user_id=current_user.id,
                             status="pending", request_date=datetime.now())

    if current_user not in team.users:
        db.session.add(req)
        db.session.commit()

        emails_leaders = [tl.email for tl in team.get_leaders()]
        send_email_utility('Richiesta di registrazione nel team',
                           f"{current_user.username} ha richiesto di registrarsi nel {team.name}, controlla la tua pagina 'gestisci squadra'!", AUTO_MAIL, emails_leaders)
        return redirect(url_for("team_home", team_id=team_id, requests_to_join=req))


@app.route('/withdraw_request_enrollment/<int:request_id>/<int:team_id>', methods=['GET', 'POST'])
@login_required
def withdraw_request_enrollment(request_id, team_id):

    request_to_remove = RequestsToJoinTeam.query.get(request_id)
    db.session.delete(request_to_remove)
    db.session.commit()

    return redirect(url_for("team_home", team_id=team_id))


@app.route('/strava_synch', methods=["GET", "POST"])
@login_required
def strava_synch():
    return redirect(url_for("authorize"))


@app.route('/trips_from_strava', methods=["GET", "POST"])
@login_required
def trips_from_strava():

    strava_token = session.get('strava_token', None)
    if strava_token:
        strava_client = StravaIO(
            access_token=strava_token)
        activities = strava_client.get_logged_in_athlete_activities()
        existing_strava_ids = [
            trip.strava_id for trip in current_user.get_trips()]
        activities_not_in_db = [
            activity for activity in activities if activity.id not in existing_strava_ids]
        return render_template('trips_from_strava.html', activities=activities_not_in_db)
    else:
        flash("Sincronizza il tuo account con strava prima di sincronizzare i giri!")
        return redirect(url_for("user_profile"))
