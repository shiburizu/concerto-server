from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
import random,os,datetime
import json
import requests

app = Flask(__name__)

REPO_KEY = os.environ['REPO_KEY']

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_CONCERTO']
#app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'

db = SQLAlchemy(app)

filter = json.load(open('bad_words.json'))

aliases = json.load(open('aliases.json'))

class Lobby(db.Model):
    uid = db.Column(db.Integer, primary_key=True, unique=True)

    code = db.Column(db.Integer, nullable=False, unique=True) #code used by players
    secret = db.Column(db.Integer, nullable=False) #secret for authentication
    last_id = db.Column(db.Integer, nullable=False) #last player ID assigned to stay unique
    type = db.Column(db.String(32), nullable=False) #lobby type for filtering
    alias = db.Column(db.String(16), nullable=True) #vanity alias
    game = db.Column(db.String(16), nullable = True) #if None, MBAACC lobby

    def __init__(self,new_id,type,game=None):
        self.secret = random.randint(1000,9999) #secret required for lobby actions
        self.code = new_id
        self.last_id = 1 #last ID assigned to keep IDs unique
        if type:
            self.type = type
        else:
            self.type = 'Private'
        if game:
            self.game = game
        else:
            self.game = 'mbaacc' #default behavior

    def find_game(self):
        for i in self.players:
            if i.status == "playing" and i.ip != None:
                return i.ip
        return None

    def prune(self):
        now = datetime.datetime.now()
        for i in self.players:
            if (now-i.last_ping).total_seconds() > 20:
                self.leave(i.lobby_id)

    def response(self,player_id,msg='OK'):
        self.prune()
        p = self.validate_id(player_id)
        if p:
            p.last_ping = datetime.datetime.now()
            db.session.add(p)
            db.session.commit()
            resp = {
                'id' : self.code,
                'status' : 'OK',
                'msg' : msg,
                'idle' : [[i.name,i.lobby_id] for i in self.players if i.status == 'idle'],
                'playing' : self.playing(),
                'challenges' : self.challenges(player_id),
                'alias' : self.alias
            }
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
            if i.target == player_id and i.status != 'playing' and i.ip != None:
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
            if ip:
                p.target = target
                p.ip = ip
                db.session.add(p)
                db.session.commit()
                return gen_resp('OK','OK')
            return gen_resp('IP not provided','FAIL')
        else:
            return gen_resp('Not in lobby.','FAIL')

    def pre_accept(self,id,target): #set target to potential player
        p1 = self.validate_id(target)
        p2 = self.validate_id(id)
        if p1 and p2:
            p2.target = target
            db.session.add(p2)
            db.session.commit()
            return gen_resp('OK','OK')
        else:
            return gen_resp('Not in lobby.','FAIL')

    def set_accept(self,id,target,ip=None):
        player = self.validate_id(id)
        if player and self.validate_id(target):
            player.target = target
            if ip != None:
                player.ip = ip
            player.status = "playing"
            db.session.add(player)
            db.session.commit()

    def accept_challenge(self,id,target):
        p1 = self.validate_id(target)
        p2 = self.validate_id(id)
        if p1 and p2:
            ip = None
            try:
                if len(p1.ip) > 0:
                    ip = p1.ip
            except:
                pass
            try:
                if len(p2.ip) > 0:
                    if ip == None:
                        ip = p2.ip
            except:
                pass
            self.set_accept(id,target,ip)
            self.set_accept(target,id,ip)
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
        return gen_resp('OK','OK')

class Player(db.Model):
    uid = db.Column(db.Integer, primary_key=True, unique=True) #id in the table

    lobby_id = db.Column(db.Integer, nullable=False) #id in the lobby
    name = db.Column(db.String(20), nullable=False) #player name
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

def valid_name(name):
    if name.lower() not in filter: #cheap method first
        for i in filter:
            if i in name.lower():
                return False
        return True
    else:
        return False

@app.before_first_request
def create_tables():
    db.create_all()

@app.route('/v')
def version_check():
    action = request.args.get('action')
    version = request.args.get('version')
    name = request.args.get('name')
    if action == 'login':
        #return gen_resp('OK','OK')
        try: #TODO this should probably have a separate game lookup for version after we get EFZ live
            current_version = requests.get('https://api.github.com/repos/shiburizu/concerto-mbaacc/releases/latest',headers={'Authorization':'token %s' % REPO_KEY})
            current_version.raise_for_status()
            version_tag = current_version.json()["tag_name"]
        except:
            print("FAILED TO GET GITHUB INFO")
            version_tag = None
        if version_tag == None or version == version_tag:
            if valid_name(name):
                return gen_resp('OK','OK')
            else:
                return gen_resp('Your name contains banned words. The filter may overreach or cause unintended blocks. Please refer to the "help" section at concerto.shib.live for guidance on reporting potential false positives.','FAIL')
        else:
            return gen_resp('UPDATE','FAIL')
    return gen_resp('No action found.','FAIL')
    
@app.route('/public') #public lobby list
def public():
    g = request.args.get('game')
    if g is None:
        g = 'mbaacc'
    lobby_resp = {}
    lobbies = purge_old(Lobby.query.filter_by(type = "Public",game = g).filter(Lobby.players.any()).order_by(Lobby.code).all())
    
    for l in lobbies:

        lobby = {}
        #'title': 'Lobby #' + str(l.code),
        #'url': 'https://invite.meltyblood.club/' + str(l.code),
        #'color': 9906987
        playing = ""
        idle = "" 
        found_ids = [] 

        for p in l.players:
            if p.status == 'playing' and p.lobby_id not in found_ids and p.target not in found_ids and p.ip is not None:
                playing += p.name + ' vs ' + l.name_by_id(p.target) + '\n'
                found_ids.append(p.lobby_id)
                found_ids.append(p.target)
            if p.status == 'idle':
                idle += p.name + '\n'

        if playing != "":
            lobby['playing'] = playing
        if idle != "":
            lobby['idle'] = idle

        lobby_resp[str(l.code)] = lobby
        if len(lobby_resp) >= 10:
            break

    #clear private players
    purge_old(Lobby.query.filter_by(type = "Private").all())
    players = db.session.query(Player).count()
    lobby_resp['Players'] = players

    #data = {
    #    'content': '**__Public Lobbies__**\nLobbies created with Concerto: <https://concerto.shib.live>\n%s connected to lobbies. List updated every 10 minutes.\n' % players,
    #    'embeds': embeds 
    #}
    #if lobbies != []:
    #    data['content'] += "Click on the lobby name to join."

    return lobby_resp

@app.route('/cast') #povertycast hook
def cast():
    l = purge_old(Lobby.query.filter_by(type = "Public", game = 'mbaacc').filter(Lobby.players.any()).order_by(Lobby.code).all())
    for i in l:
        ip = i.find_game()
        if ip != None:
            return "<a href='concerto://watch:%s'>GAME FOUND</a>" % ip
    return "NOT FOUND"

@app.route('/s') #statistics
def stats():
    g = request.args.get('game')
    if g is None:
        g = 'mbaacc'
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
        lst = purge_old(Lobby.query.filter_by(type = "Public", game = g).filter(Lobby.players.any()).limit(l).order_by(Lobby.code).all())
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
        if lobby_id in aliases:
            resp = gen_resp('OK','OK')
            resp.update({'type':'Private'})
            return resp
        try:
            int(lobby_id)
        except ValueError:
            return gen_resp('Invalid lobby ID','FAIL')
        else:
            l = purge_old([Lobby.query.filter_by(code=int(lobby_id)).first()])
            if l != []:
                resp = gen_resp('OK','OK')
                resp.update({'type':l[0].type})
                return resp
            return gen_resp('Lobby does not exist.','FAIL')
    return gen_resp('Invalid stats action','FAIL')


def create_lobby(player_name,type,alias=None,game='mbaacc'):
    if player_name:
        new_id = random.randint(1000,9999)
        while True:
            l = Lobby.query.filter_by(code=new_id).first()
            if l:
                if purge_old([l]) != []:
                    new_id = random.randint(1000,9999)
            else:
                break
        new_room = Lobby(new_id,type,game)
        new_player = Player(player_name,1)
        new_room.players.append(new_player)
        if alias:
            if alias in aliases:
                new_room.alias = alias
        db.session.add(new_room)
        db.session.add(new_player)
        db.session.commit()
        r = new_room.response(1,msg=1)
        r['secret'] = new_room.secret
        r['type'] = new_room.type
        return r
    else:
        return gen_resp('No player name for creator provided.','FAIL')

def list_lobbies(game='mbaacc'):
    l = purge_old(Lobby.query.filter_by(type = "Public",game=game).filter(Lobby.players.any()).order_by(Lobby.code).all())
    resp = {
        'msg' : 'OK',
        'status' : 'OK',
        'lobbies' : [[i.code,i.game,len(i.players)] for i in l]
    }
    return resp

def join_lobby(lobby_id,player_name,game='mbaacc'):
    #validation
    if not lobby_id:
        return gen_resp('Lobby ID is empty','FAIL')
    if len(lobby_id) > 16:
        return gen_resp('Invalid lobby code','FAIL')
    #check if code is in alias list
    if lobby_id in aliases:
        if player_name: #prevent aliases from being used in 2 games at the same time for now
            l = Lobby.query.filter_by(alias=lobby_id).first()
            if l:
                if game == l.game:
                    l.prune()
                    p = l.join(player_name)
                    resp = l.response(p,msg=p)
                    resp['secret'] = l.secret
                    resp['type'] = l.type
                    return resp
                else:
                    return gen_resp('Lobby alias is being used in a different game!','FAIL')
            else:
                return create_lobby(player_name,"Private",alias=lobby_id,game=game)
        else:
            return gen_resp('No player name provided.','FAIL')
    #not in aliases, so check by number codes
    try:
        int(lobby_id)
    except ValueError:
        return gen_resp('Invalid lobby code.','FAIL')
    else:
        if player_name:
            l = Lobby.query.filter_by(code=int(lobby_id)).first()
            if l:
                l.prune()
                if l.players != []:
                    if l.game == game:
                        p = l.join(player_name)
                        resp = l.response(p,msg=p)
                        resp['secret'] = l.secret
                        resp['type'] = l.type
                        return resp
                    else:
                        return gen_resp('Lobby not found.','FAIL')
                else:
                    db.session.delete(l)
                    db.session.commit()
                    return gen_resp('Empty lobby found.','FAIL')
            return gen_resp('Lobby not found.','FAIL')
        return gen_resp('No player name provided.','FAIL')

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
    game = request.args.get('game')
    for key in request.args:
        print(request.args.get(key))
        print(request.args.getlist(key))
    if game == None:
        game = 'mbaacc'
    if action == "create":
        return create_lobby(player_name,type,game)
    elif action == "join":
        return join_lobby(lobby_id,player_name,game)
    elif action == "list":
        return list_lobbies(game)
    elif lobby_id and secret:
        try:
            int(secret)
        except ValueError:
            return gen_resp('Lobby handshake failed.','FAIL')
        l = Lobby.query.filter_by(alias=lobby_id,game=game).first()
        if not l:
            try:
                l = Lobby.query.filter_by(code=int(lobby_id)).first()
            except ValueError:
                return gen_resp('Invalid lobby code.','FAIL')
        if l:
            if l.secret == int(secret):
                if action == "challenge":
                    return l.send_challenge(int(player_id),int(target_id),player_ip)
                elif action == "pre_accept":
                    return l.pre_accept(int(player_id),int(target_id))
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

'''
if __name__ == '__main__':
	port = int(os.environ.get('PORT', 5000))
	app.run(host='0.0.0.0', port=port, debug=False)
'''
