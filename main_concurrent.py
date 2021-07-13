from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
import random,os,datetime
app = Flask(__name__)

CURRENT_VERSION = '7-5-2021'

basedir = os.path.abspath(os.path.dirname(__file__))

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///concerto.db'

db = SQLAlchemy(app)

class Lobby(db.Model):
    uid = db.Column(db.Integer, primary_key=True)

    code = db.Column(db.Integer, nullable=False) #code used by players
    secret = db.Column(db.Integer, nullable=False) #secret for authentication
    last_id = db.Column(db.Integer, nullable=False) #last player ID assigned to stay unique
    type = db.Column(db.String(32), nullable=False) #lobby type for filtering

    def __init__(self,new_id,type):
        self.secret = random.randint(1000,9999) #secret required for lobby actions
        self.code = new_id
        self.last_id = 1 #last ID assigned to keep IDs unique
        if type:
            self.type = type
        else:
            self.type = 'Private'

    def response(self,player_id,msg='OK'):
        resp = {
            'id' : self.code,
            'status' : 'OK',
            'msg' : msg,
            'idle' : [[i.name,i.lobby_id] for i in self.players],
            'playing' : self.playing(),
            'challenges' : self.challenges(player_id)
        }
        print(resp)
        return resp

    def playing(self):
        found_ids = []
        resp = []
        for i in self.players:
            if i.status == 'playing' and i.lobby_id not in found_ids and i.target not in found_ids:
                resp.append([i.name,self.name_by_id(i.target),i.lobby_id,i.target,i.ip])
                found_ids.append(i.id)
                found_ids.append(i.target)
        return resp

    def challenges(self,player_id):
        resp = []
        for i in self.players:
            if i.target == player_id and i.status != 'playing':
                resp.append([i.name,i.id,i.ip])
        return resp

    def name_by_id(self,id): #this could be faster
        for i in self.players:
            if i.lobby_id == id:
                return i.name
        return None

class Player(db.Model):
    uid = db.Column(db.Integer, primary_key=True) #id in the table

    lobby_id = db.Column(db.Integer, nullable=False) #id in the lobby
    name = db.Column(db.String(16), nullable=False) #player name
    last_ping = db.Column(db.DateTime, nullable=False) #timestamp of last ping
    status = db.Column(db.String(32), nullable=False) #current status
    ip = db.Column(db.String(32), nullable=True) #IP if challenging
    target = db.Column(db.Integer, nullable=True) #target if challenging

    #relationship to lobby
    lobby_code = db.Column(db.Integer, db.ForeignKey('lobby.code'), nullable = False)
    lobby = db.relationship('Lobby',backref=db.backref('players'),lazy=True)

    def __init__(self,new_name,new_id):
        self.lobby_id = new_id
        self.name = new_name
        self.last_ping = datetime.datetime.now()
        self.status = 'idle'
        self.ip = None
        self.target = None


def gen_resp(msg,status):
    resp = {
        'status' : status,
        'msg' : msg
    }
    return resp

@app.before_first_request
def create_tables():
    db.create_all()

@app.route('/v')
def version_check():
    if request.args.get('action') == 'check':
        if request.args.get('version') == CURRENT_VERSION:
            return gen_resp('OK','OK')
        else:
            return gen_resp('A newer version is available. Visit concerto.shib.live to update.','FAIL')

@app.route('/l') #lobby functions
def lobby_server():
    action = request.args.get('action')
    lobby_id = request.args.get('id')
    player_name = request.args.get('name')
    player_id = request.args.get('p')
    target_id = request.args.get('t')
    player_ip = request.args.get('ip')
    secret = request.args.get('secret')
    type = request.args.get('type')
    
    if action == 'create':
        if player_name:
            new_id = random.randint(1000,9999)
            while True:
                if Lobby.query.filter_by(code=new_id).first() is None:
                    break
                else:
                    new_id = random.randint(1000,9999)
            new_room = Lobby(new_id,type)
            new_player = Player(player_name,1)
            new_room.players.append(new_player)
            db.session.add(new_room)
            db.session.add(new_player)
            db.session.commit()
            r = new_room.response(1,msg=1)
            #r['secret'] = new_room.secret
            return r


if __name__ == '__main__':
	port = int(os.environ.get('PORT', 5000))
	app.run(host='0.0.0.0', port=port, debug=False)