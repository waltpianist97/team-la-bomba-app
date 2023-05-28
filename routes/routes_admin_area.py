from app import app, db
from flask import request, render_template, flash, redirect,url_for
from flask_login import current_user, login_user, logout_user,login_required
from sqlalchemy import or_, and_, desc, func
from models import User, Trip, Team, TeamUserAssociation, RequestsToJoinTeam
from forms import *
from werkzeug.urls import url_parse
import secrets
from datetime import datetime, timedelta
import smtplib
from tools import AUTO_MAIL, send_email_utility

#%% ADMIN SECTION

#%% ADMIN SECTION
@app.route('/admin_home',methods=['GET', 'POST'])
@login_required
def admin_home():
    
    users = User.query.filter(User._is_admin==None).all()
    trips = Trip.query.all()
    teams = Team.query.all()


    if trips is None:
        trips = []
    if teams is None:
        teams = []
    if users is None:
        users = []

    return render_template('admin_home.html', users=users,trips=trips,teams=teams)


@app.route('/enroll_directly/<int:team_id>/<int:user_id>',methods=['GET', 'POST'])
@login_required
def enroll_directly(team_id,user_id):
    
    user = User.query.get(user_id)
    team = Team.query.get(team_id)

    #if the team has no member, the first joining becomes leader
    if not team.users: 
        team.add_member(user,role="team_leader")
    else:
        team.add_member(user,role="user")

    db.session.commit()

    eventual_requests_to_eliminate =  RequestsToJoinTeam.query.filter(and_(RequestsToJoinTeam.user_id==user.id,RequestsToJoinTeam.team_id==team.id)).all()
    [db.session.delete(req_to_eliminate) for req_to_eliminate in eventual_requests_to_eliminate]

    db.session.commit()

    if current_user._is_admin:
        return redirect(url_for("view_user_profile_by_admin",user_id=user.id))
    else:
        return redirect(url_for("team_home",team_id=team.id))


@app.route("/view_user_profile_by_admin/<int:user_id>")
@login_required
def view_user_profile_by_admin(user_id):
    user = User.query.get(user_id)
    teams= Team.query.all()
    team_roles = []
    for team in teams:
        t_r = TeamUserAssociation.query.filter(and_(TeamUserAssociation.user_id==user.id,TeamUserAssociation.team_id==team.id)).first()
        role=None
        if t_r: 
            role=t_r.role
        team_roles.append({"team":team,"team_role":role})
    return render_template("view_user_profile_by_admin.html",user=user,team_roles=team_roles)
 

@app.route("/delete_team/<int:team_id>")
@login_required
def delete_team(team_id):
    team = Team.query.filter_by(id=team_id).first()
    db.session.delete(team)
    db.session.commit()
    return redirect(url_for("admin_home",username=current_user.username))


@app.route('/new_team',methods=['GET', 'POST'])
@login_required
def new_team():
    if not current_user._is_admin:
        return 'Unauthorized'

    form = NewTeamForm()
    if form.validate_on_submit():
        team = Team(name=form.name.data,description=form.description.data)
       
        db.session.add(team)
        db.session.commit()
        flash('New team registered!')
        return redirect(url_for('admin_home',username = current_user.username))

    return render_template('new_team.html',title="Add new team", form = form )


@app.route("/delete_user/<int:user_id>")
@login_required
def delete_user(user_id):
    user = User.query.filter_by(id=user_id).first()
    db.session.delete(user)
    db.session.commit()
    if current_user._is_admin:
        return redirect(url_for("admin_home",username=current_user.username))
    else:
        return redirect(url_for("index"))

