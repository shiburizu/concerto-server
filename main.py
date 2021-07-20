from flask import Flask, request, redirect
from flask_sqlalchemy import SQLAlchemy
import random,os,datetime
app = Flask(__name__)

CURRENT_VERSION = ['7-19-2021r2','7-20-2021']

basedir = os.path.abspath(os.path.dirname(__file__))

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_CONCERTO']

db = SQLAlchemy(app)

class Lobby(db.Model):
    uid = db.Column(db.Integer, primary_key=True, unique=True)

    code = db.Column(db.Integer, nullable=False, unique=True) #code used by players
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

    def prune(self):
        now = datetime.datetime.now()
        for i in self.players:
            if (now-i.last_ping).total_seconds() > 10:
                self.leave(i.lobby_id)

    def response(self,player_id,msg='OK'):
        self.prune()
        p = self.validate_id(player_id)
        if p:
            p.last_ping = datetime.datetime.now()
            db.session.add(p)
            db.session.commit()
            self.prune()
            resp = {
                'id' : self.code,
                'status' : 'OK',
                'msg' : msg,
                'idle' : [[i.name,i.lobby_id] for i in self.players if i.status == 'idle'],
                'playing' : self.playing(),
                'challenges' : self.challenges(player_id)
            }
            #print(resp)
            return resp
        return gen_resp('Not in lobby.','FAIL')

    def join(self,new_player):
        self.last_id += 1
        p = Player(new_player,self.last_id)
        self.players.append(p)
        db.session.add(p)
        db.session.add(self)
        db.session.commit()
        return self.last_id

    def playing(self):
        found_ids = []
        resp = []
        for i in self.players:
            if i.status == 'playing' and i.lobby_id not in found_ids and i.target not in found_ids and i.ip is not None:
                resp.append([i.name,self.name_by_id(i.target),i.lobby_id,i.target,i.ip])
                found_ids.append(i.lobby_id)
                found_ids.append(i.target)
        return resp

    def challenges(self,player_id):
        resp = []
        for i in self.players:
            if i.target == player_id and i.status != 'playing':
                resp.append([i.name,i.lobby_id,i.ip])
        return resp

    def name_by_id(self,id): #this could be faster
        for i in self.players:
            if i.lobby_id == id:
                return i.name
        return None

    def validate_id(self,id):
        for i in self.players:
            if i.lobby_id == id:
                return i
        return None

    def send_challenge(self,id,target,ip):
        p = self.validate_id(id)
        if p:
            p.target = target
            p.ip = ip
            db.session.add(p)
            db.session.commit()
            return gen_resp('OK','OK')
        else:
            return gen_resp('Not in lobby.','FAIL')

    def accept_challenge(self,id,target):
        p1 = self.validate_id(target)
        p2 = self.validate_id(id)
        if p1 and p2:
            p1.status = "playing"
            p2.status = "playing"
            p2.target = target
            db.session.add(p1)
            db.session.add(p2)
            db.session.commit()
            return gen_resp('OK','OK')
        else:
            return gen_resp('Not in lobby.','FAIL')

    def end(self,id):
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
            p1.status = "idle"
            p1.target = None
            p1.ip = None
            db.session.add(p1)
            db.session.commit()
            return gen_resp('OK','OK')
        return gen_resp('Not in lobby.','FAIL')

    def leave(self,id):
        p1 = self.validate_id(id)
        if p1:
            if p1.target:
                p2 = self.validate_id(p1.target)
                if p2:
                    p2.status = "idle"
                    p2.target = None
                    p2.ip = None
                    db.session.add(p2)
            self.players.remove(p1)
            db.session.delete(p1)
            db.session.commit()
        return gen_resp('OK','OK')

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

@app.route('/v')
def version_check():
    if request.args.get('action') == 'check':
        if request.args.get('version') in CURRENT_VERSION:
            return gen_resp('OK','OK')
        else:
            return gen_resp('A newer version is available. Visit concerto.shib.live to update.','FAIL')

@app.route('/i/<id>')
def lobby_link(id):
    if id:
        return redirect("concerto://lobby:%s" % id)

@app.route('/s') #statistics
def stats():
    action = request.args.get('action')
    limit = request.args.get('limit')
    lobby_id = request.args.get('id')
    if action == 'list':
        l = 8
        if limit:
            try:
                l = int(limit)
            except ValueError:
                return gen_resp('Bad limit argument.','FAIL')
        lst = purge_old(Lobby.query.filter_by(type = "Public").limit(l).all())
        resp = {}
        for n in lst:
            lobby = {
                'idle' : [i.name for i in n.players if i.status == 'idle'],
            }
            found_ids = []
            p = []
            for i in n.players:
                if i.status == 'playing' and i.lobby_id not in found_ids and i.target not in found_ids and i.ip is not None:
                    p.append([i.name,n.name_by_id(i.target)])
                    found_ids.append(i.lobby_id)
                    found_ids.append(i.target)
            lobby.update({'playing':p})
            resp.update({n.code:lobby})
        return resp
    elif action == 'check':
        l = purge_old([Lobby.query.filter_by(code=int(lobby_id)).first()])
        if l != []:
            resp = gen_resp('OK','OK')
            resp.update({'type':l.type})
            return resp
        return gen_resp('Lobby does not exist.','FAIL')
    return gen_resp('Invalid stats action','FAIL')

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
            r['secret'] = new_room.secret
            return r
    elif action == "list":
        l = purge_old(Lobby.query.filter_by(type = "Public").all())
        resp = {
            'msg' : 'OK',
            'status' : 'OK',
            'lobbies' : [[i.code,len(i.players)] for i in l]
        }
        #print(resp)
        return resp
    elif action == "join" and lobby_id:
        try:
            int(lobby_id)
        except ValueError:
            return gen_resp('Invalid lobby code.','FAIL')
        if player_name:
            l = Lobby.query.filter_by(code=int(lobby_id)).first()
            if l:
                l.prune()
                if l.players != []:
                    p = l.join(player_name)
                    resp = l.response(p,msg=p)
                    resp['secret'] = l.secret
                    return resp
                else:
                    db.session.delete(l)
                    db.session.commit()
                    return gen_resp('Empty lobby found.','FAIL')
            return gen_resp('Lobby not found.','FAIL')
        return gen_resp('No player name provided.','FAIL')
    elif lobby_id and secret:
        try:
            int(lobby_id)
            int(secret)
        except ValueError:
            return gen_resp('Invalid lobby code.','FAIL')
        l = Lobby.query.filter_by(code=int(lobby_id)).first()
        if l:
            if l.secret == int(secret):
                if action == "challenge":
                    return l.send_challenge(int(player_id),int(target_id),player_ip)
                elif action == "accept":
                    return l.accept_challenge(int(player_id),int(target_id))
                elif action == "end":
                    return l.end(int(player_id))
                elif action == "leave":
                    resp = l.leave(int(player_id))
                    if len(l.players) == 0:
                        db.session.delete(l)
                        db.session.commit()
                    return resp
                elif action == "status":
                    return l.response(int(player_id))
                return gen_resp('lobby action failed','FAIL')
        else:
            return gen_resp('No lobby found','FAIL')
    return gen_resp('No action match','FAIL')

if __name__ == '__main__':
	port = int(os.environ.get('PORT', 5000))
	app.run(host='0.0.0.0', port=port, debug=False)