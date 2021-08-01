from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
import os,datetime
import requests
import json
app = Flask(__name__)

DISCORD_KEY = os.environ['DISCORD_KEY'] #to send requests to the secondary server

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_CONCERTO']

db = SQLAlchemy(app)

class Lobby(db.Model):
    uid = db.Column(db.Integer, primary_key=True, unique=True)

    code = db.Column(db.Integer, nullable=False, unique=True) #code used by players
    secret = db.Column(db.Integer, nullable=False) #secret for authentication
    last_id = db.Column(db.Integer, nullable=False) #last player ID assigned to stay unique
    type = db.Column(db.String(32), nullable=False) #lobby type for filtering

    def prune(self):
        now = datetime.datetime.now()
        for i in self.players:
            if (now-i.last_ping).total_seconds() > 10:
                self.leave(i.lobby_id)

    def leave(self,id):
        p1 = self.validate_id(id)
        if p1:
            if p1.target:
                p2 = self.validate_id(p1.target)
                if p2:
                    if p2.target == id: #make sure other player is targeting us
                        p2.status = "idle"
                        p2.target = None
                        p2.ip = None
                        db.session.add(p2)
            else: #iterate over players only if we do not have a target set
                for i in self.players:
                    if i.target == id:
                        i.status = "idle"
                        i.target = None
                        i.ip = None
                        db.session.add(i)
            self.players.remove(p1)
            db.session.delete(p1)
            db.session.commit()
    
    def validate_id(self,id):
        for i in self.players:
            if i.lobby_id == id:
                return i
        return None
    
    def name_by_id(self,id): #this could be faster
        for i in self.players:
            if i.lobby_id == id:
                return i.name
        return None

class Player(db.Model):
    uid = db.Column(db.Integer, primary_key=True, unique=True) #id in the table

    lobby_id = db.Column(db.Integer, nullable=False) #id in the lobby
    name = db.Column(db.String(16), nullable=False) #player name
    last_ping = db.Column(db.DateTime, nullable=False) #timestamp of last ping
    status = db.Column(db.String(32), nullable=False) #current status
    ip = db.Column(db.String(32), nullable=True) #IP if challenging
    target = db.Column(db.Integer, nullable=True) #target if challenging

    #relationship to lobby
    lobby_code = db.Column(db.Integer, db.ForeignKey('lobby.code'), nullable = False)
    lobby = db.relationship('Lobby',backref=db.backref('players'))

def purge_old(lst):
    cleanup = []
    for i in lst:
        if i is None:
            lst.remove(i)
        else:
            if i.players != []:
                i.prune()
                if i.players == []:
                    cleanup.append(i)
            else:
                cleanup.append(i)
    if cleanup != []:
        for i in cleanup:
            db.session.delete(i)
            lst.remove(i)
        db.session.commit()
    return lst

@app.before_first_request
def create_tables():
    db.create_all()

@app.route('/')
def actions():
    action = request.args.get('action')
    key = request.args.get('key')
    if key != DISCORD_KEY:
        return 'BAD'
    if action == 'webhook':
        update_webhook()
        return 'OK'

def update_webhook():
    hooks = []
    messages = []
    n = 0
    while True:
        if "DISCORD_%s" % n in os.environ and "MSG_%s" % n in os.environ:
            hooks.append(os.environ["DISCORD_%s" % n])
            messages.append(os.environ["MSG_%s" % n])
            n += 1
        else:
            break

    lobbies = purge_old(Lobby.query.filter_by(type = "Public").filter(Lobby.players.any()).all())
    embeds = []
    for l in lobbies:
        # TODO: random lobby colors would be cool and creation timestamps
        lobby = {
            'title': 'Lobby #' + str(l.code),
            'url': 'https://invite.meltyblood.club/' + str(l.code),
            'color': 9906987
        }
        playing = ""
        idle = "" 
        for p in l.players:
            found_ids = [] 
            if p.status == 'playing' and p.lobby_id not in found_ids and p.target not in found_ids and p.ip is not None:
                playing += p.name + ' vs ' + l.name_by_id(p.target) + '\n'
                found_ids.append(p.lobby_id)
                found_ids.append(p.target)
            if p.status == 'idle':
                idle += p.name + '\n'

        fields = []
        if playing:
            fields.append({'name': 'Playing', 'value': playing})
        if idle:
            fields.append({'name': 'Idle', 'value': idle})

        lobby.update({'fields': fields})
        embeds.append(lobby)
        if len(embeds) >= 10:
            break

    #clear private players
    purge_old(Lobby.query.filter_by(type = "Private").all())
    players = db.session.query(Player).count()

    data = {
        'content': '**__Public Lobbies__**\nLobbies created with Concerto: <https://concerto.shib.live>\n%s playing now.\n' % players,
        'embeds': embeds 
    }
    if lobbies != []:
        data['content'] += "Click on the lobby name to join."

    for a,b in zip(hooks,messages):
        url = a + "/messages/" + b
        resp = requests.patch(url, data=json.dumps(data), headers={'Content-Type': 'application/json'})
        resp.raise_for_status()
'''
if __name__ == '__main__':
	port = int(os.environ.get('PORT', 5000))
	app.run(host='0.0.0.0', port=port, debug=False)
'''
