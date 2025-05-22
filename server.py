import socketio
from aiohttp import web

sio = socketio.AsyncServer(async_mode='aiohttp', cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

rooms = {}
connected_clients = {} 

@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    connected_clients[sid] = None  # Not in any room yet

@sio.event
async def join(sid, data):
    try:
        room_id = str(data['room'])
        player_name = str(data.get('name', 'Anonymous')).strip()
        
        if not player_name or player_name == 'Anonymous':
            player_name = f"Player{len(connected_clients)+1}"
        
        # Check if client is already in a room
        if connected_clients.get(sid) is not None:
            print(f"[JOIN FAILED] Client {sid} is already in room {connected_clients[sid]}")
            await sio.emit('join_failed', {'message': 'You are already in a room'}, to=sid)
            return
        
        # Check if room exists and already has 2 players
        if room_id in rooms and len(rooms[room_id]['players']) >= 2:
            print(f"[JOIN FAILED] Room {room_id} is full")
            await sio.emit('room_full', {}, to=sid)
            return
        
        await sio.enter_room(sid, room_id)
        connected_clients[sid] = room_id
        
        if room_id not in rooms:
            rooms[room_id] = {
                'players': [], 
                'sids': [],
                'names': [],
                'current_turn': 'black',
                'board': [[0 for _ in range(10)] for _ in range(10)]
            }
        
        # Assign color - black to first player, white to second
        color = 'black' if len(rooms[room_id]['players']) == 0 else 'white'
        
        rooms[room_id]['players'].append(color)
        rooms[room_id]['sids'].append(sid)
        rooms[room_id]['names'].append(player_name)
        
        print(f"[JOIN] {player_name} (SID {sid}) joined room {room_id} as {color}")
        print(f"Current players in room {room_id}: {rooms[room_id]['names']} ({rooms[room_id]['players']})")
        
        # Prepare response data
        response_data = {
            'color': color,
            'currentTurn': rooms[room_id]['current_turn'],
            'board': rooms[room_id]['board'],
            'playerName': player_name,
            'roomId': room_id
        }
        
        # If there's already a player, include their name
        if len(rooms[room_id]['players']) == 2:
            opponent_index = 0 if color == 'white' else 1
            response_data['opponentName'] = rooms[room_id]['names'][opponent_index]
            # Update the first player with the new player's name
            await sio.emit('opponent_joined', {
                'opponentName': player_name,
                'opponentColor': color
            }, to=rooms[room_id]['sids'][opponent_index])
        
        await sio.emit('room_joined', response_data, to=sid)
        
        if len(rooms[room_id]['players']) == 2:
            # Notify both players that game is starting
            await sio.emit('start_game', {
                'currentTurn': rooms[room_id]['current_turn'],
                'board': rooms[room_id]['board'],
                'playerNames': {
                    'black': rooms[room_id]['names'][0],
                    'white': rooms[room_id]['names'][1]
                },
                'roomId': room_id
            }, room=room_id)
            
    except Exception as e:
        print(f"Error in join: {str(e)}")
        await sio.emit('join_error', {'message': str(e)}, to=sid)      

@sio.event
async def move(sid, data):
    room_id = data['room']
    row = data['row']
    col = data['column']
    player_value = data['player']  # 1 = white, 2 = black

    if room_id not in rooms:
        print(f"[MOVE FAILED] Room {room_id} does not exist")
        return

    room = rooms[room_id]

    # Validate it's the correct player's turn
    color = 'white' if player_value == 1 else 'black'
    if room['current_turn'] != color:
        print(f"[INVALID MOVE] Not {color}'s turn.")
        await sio.emit("invalid_move", {}, to=sid)
        return

    board = room['board']

    # Check if the cell is already occupied
    if board[row][col] != 0:
        print(f"[INVALID MOVE] Cell [{row}, {col}] is already occupied.")
        await sio.emit("invalid_move", {}, to=sid)
        return

    board[row][col] = player_value
    # Log the move
    print(f"[MOVE MADE] Player {player_value} ({color}) placed at row={row}, col={col} in room {room_id}")

    print(board)

    # Switch turns
    room['current_turn'] = 'black' if color == 'white' else 'white'

    # Broadcast move to all players
    await sio.emit("move_made", {
        'row': row,
        'column': col,
        'player': player_value,
        'board': board,
        'currentTurn': room['current_turn']
    }, room=room_id)

@sio.event
async def win(sid, data):
    room_id = data['room']
    winner = 'white' if data['winner'] == 1 else 'black'
    print(f"[WIN] Player {winner} won the game in room {room_id}")
    await sio.emit('game_over', data, room=room_id)

@sio.event
async def disconnect(sid):
    print(f"[DISCONNECT] Client disconnected: {sid}")
    room_id = connected_clients.get(sid)
    
    if room_id and room_id in rooms:
        # Remove player from room
        if sid in rooms[room_id]['sids']:
            index = rooms[room_id]['sids'].index(sid)
            color = rooms[room_id]['players'][index]
            player_name = rooms[room_id]['names'][index]
            
            rooms[room_id]['players'].pop(index)
            rooms[room_id]['sids'].pop(index)
            rooms[room_id]['names'].pop(index)
            
            print(f"[LEAVE] Player {player_name} ({color}) left room {room_id}")
            
            if rooms[room_id]['sids']:
                # Notify remaining player
                await sio.emit('opponent_left', {
                    'color': color,
                    'name': player_name
                }, room=room_id)
            else:
                # Room is empty, remove it
                print(f"Room {room_id} is now empty and removed")
                del rooms[room_id]
    
    # Remove from connected clients
    if sid in connected_clients:
        del connected_clients[sid]
        
if __name__ == '__main__':
    print("Starting Socket.IO server on port 6789")
    web.run_app(app, port=6789)