import pygame
import sys
import os
import json
from datetime import datetime

pygame.init()

WIDTH, HEIGHT = 1000, 700
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Cog World — Main Game")

FONT_MAIN = pygame.font.SysFont(None, 28)
FONT_INPUT = pygame.font.SysFont(None, 32)

clock = pygame.time.Clock()

# -------------------------
# FILE PATHS
# -------------------------
PLAYER_FILE = "player-1.json"

# -------------------------
# WORLD / PLAYER STATE
# -------------------------

player_x = 0
player_y = 0
player_z = 0
player_health = 100
player_inventory = []

current_room = {
    "description": "You are nowhere. (Room failed to load.)",
    "exits": {},
    "items": []
}

DIRS = {
    "n":  (0,  1, 0),
    "ne": (1,  1, 0),
    "e":  (1,  0, 0),
    "se": (1, -1, 0),
    "s":  (0, -1, 0),
    "sw": (-1,-1, 0),
    "w":  (-1, 0, 0),
    "nw": (-1, 1, 0),
}

message_log = [
    "Welcome to Cog World.",
    "Type 'look' to inspect the room.",
    "Type n/s/e/w/ne/nw/se/sw to move.",
    "You can 'look trunk' to peek inside something.",
    "Use 'get <item>' to pick something up.",
]
command_input = ""

# -------------------------
# PLAYER LOAD/SAVE
# -------------------------

def load_player():
    global player_x, player_y, player_z, player_health, player_inventory
    if not os.path.exists(PLAYER_FILE):
        data = {
            "name": "Player One",
            "stats": {"health": 100},
            "position": {"x": 0, "y": 0, "z": 0},
            "inventory": [],
            "meta": {"last_save": None}
        }
        with open(PLAYER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return

    try:
        with open(PLAYER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        pos = data.get("position", {})
        player_x = pos.get("x", 0)
        player_y = pos.get("y", 0)
        player_z = pos.get("z", 0)

        stats = data.get("stats", {})
        player_health = stats.get("health", 100)

        player_inventory[:] = data.get("inventory", [])

        message_log.append("Player data loaded from player-1.json.")
    except Exception as e:
        message_log.append(f"Error loading player file: {e}")

def save_player():
    data = {
        "name": "Player One",
        "stats": {"health": player_health},
        "position": {"x": player_x, "y": player_y, "z": player_z},
        "inventory": player_inventory,
        "meta": {"last_save": datetime.utcnow().isoformat() + "Z"}
    }
    try:
        with open(PLAYER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        message_log.append(f"Error saving player file: {e}")

# -------------------------
# HELPERS: WORLD + ITEMS
# -------------------------

def pad(n: int) -> str:
    return f"-{abs(n):02d}" if n < 0 else f"{n:02d}"

def room_filename(x, y, z):
    folder = "world_tiles"
    return os.path.join(folder, f"{pad(x)}-{pad(y)}-{pad(z)}.json")

def load_room(x, y, z):
    path = room_filename(x, y, z)

    if not os.path.exists(path):
        return {
            "description": "(This room does not exist yet.)",
            "exits": {},
            "items": []
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_exits = data.get("exits", {})
        exits_clean = {d: bool(raw_exits.get(d, False)) for d in ["n","ne","e","se","s","sw","w","nw"]}
        desc = data.get("description", "").strip()
        its = data.get("items", [])
        if not isinstance(its, list):
            its = []

        return {"description": desc, "exits": exits_clean, "items": its}
    except Exception as e:
        return {"description": f"(Error loading room: {e})", "exits": {}, "items": []}

def list_top_level_items(items_list):
    lines = []
    for it in items_list:
        nm = it.get("name", "???")
        ds = it.get("desc", "").strip()
        if ds:
            lines.append(f"- {nm}: {ds}")
        else:
            lines.append(f"- {nm}")
    return lines

def find_item_recursive_and_remove(items_list, target_name):
    target_name = target_name.lower().strip()
    for i, it in enumerate(items_list):
        if it.get("name", "").lower().strip() == target_name:
            return items_list.pop(i)
    for it in items_list:
        kids = it.get("contains", [])
        if isinstance(kids, list) and kids:
            got = find_item_recursive_and_remove(kids, target_name)
            if got is not None:
                return got
    return None

def find_item_by_name(items_list, target_name):
    target_name = target_name.lower().strip()
    for it in items_list:
        if it.get("name", "").lower().strip() == target_name:
            return it
    return None

def describe_container(item):
    nm = item.get("name", "something")
    ds = item.get("desc", "").strip()
    if ds:
        message_log.append(f"{nm}: {ds}")
    kids = item.get("contains", [])
    if kids and isinstance(kids, list) and len(kids) > 0:
        message_log.append(f"Inside {nm}:")
        for child in kids:
            message_log.append(f"- {child.get('name','???')}: {child.get('desc','').strip()}")
    else:
        message_log.append(f"{nm} is empty.")

def describe_current_room():
    room = current_room
    if room["description"]:
        for line in room["description"].split("\n"):
            message_log.append(line)
    open_exits = [d for d, ok in room["exits"].items() if ok]
    if open_exits:
        message_log.append("Exits: " + ", ".join(open_exits))
    else:
        message_log.append("There are no visible exits.")
    if room["items"]:
        message_log.append("You see:")
        for line in list_top_level_items(room["items"]):
            message_log.append(line)
    else:
        message_log.append("You see nothing of interest.")

def try_move(direction):
    global player_x, player_y, player_z, current_room
    direction = direction.lower()
    if direction not in DIRS:
        message_log.append(f"You can't go '{direction}'.")
        return
    if not current_room["exits"].get(direction, False):
        message_log.append("You can't go that way.")
        return
    dx, dy, dz = DIRS[direction]
    player_x += dx
    player_y += dy
    player_z += dz
    current_room = load_room(player_x, player_y, player_z)
    message_log.append(f"You move {direction}.")
    describe_current_room()
    save_player()  # auto-save after moving

# -------------------------
# RENDERING
# -------------------------

def draw_text_block(lines, x, y, w, h, font, color=(220,220,220)):
    visible_lines = []
    total_h = 0
    line_h = font.get_height() + 4
    for line in reversed(lines):
        if total_h + line_h > h:
            break
        visible_lines.append(line)
        total_h += line_h
    draw_y = y + h - line_h
    for line in visible_lines:
        img = font.render(line, True, color)
        screen.blit(img, (x + 8, draw_y))
        draw_y -= line_h

def render_scene():
    screen.fill((15,20,30))
    bar_rect = pygame.Rect(0, 0, WIDTH, 32)
    pygame.draw.rect(screen, (25,30,45), bar_rect)
    pygame.draw.line(screen, (80,100,140), (0, 32), (WIDTH, 32), 2)
    cmds = ["look", "look [name]", "get [name]", "inventory", "go [n/s/e/w]", "quit"]
    bar_text = "   Commands:  " + " · ".join(cmds)
    bar_img = FONT_MAIN.render(bar_text, True, (180,200,255))
    screen.blit(bar_img, (18, 7))
    log_rect = pygame.Rect(20, 40, WIDTH - 40, HEIGHT - 160)
    pygame.draw.rect(screen, (40,45,60), log_rect, border_radius=8)
    pygame.draw.rect(screen, (120,130,160), log_rect, width=2, border_radius=8)
    draw_text_block(message_log, log_rect.x, log_rect.y, log_rect.w, log_rect.h, FONT_MAIN)
    hud_rect = pygame.Rect(20, HEIGHT - 110, WIDTH - 40, 30)
    pygame.draw.rect(screen, (30,35,50), hud_rect, border_radius=8)
    pygame.draw.rect(screen, (90,100,130), hud_rect, width=1, border_radius=8)
    hud_text = f"Location: ({player_x},{player_y},{player_z})   Health: {player_health}   Inventory: {len(player_inventory)} items"
    hud_img = FONT_MAIN.render(hud_text, True, (200,200,220))
    screen.blit(hud_img, (hud_rect.x + 8, hud_rect.y + 5))
    input_rect = pygame.Rect(20, HEIGHT - 70, WIDTH - 40, 50)
    pygame.draw.rect(screen, (40,45,60), input_rect, border_radius=8)
    pygame.draw.rect(screen, (120,200,255), input_rect, width=2, border_radius=8)
    prompt = "> " + command_input
    prompt_img = FONT_INPUT.render(prompt, True, (255,255,255))
    screen.blit(prompt_img, (input_rect.x + 8, input_rect.y + 12))
    pygame.display.flip()

# -------------------------
# COMMAND HANDLERS
# -------------------------

def handle_get_command(tokens):
    if len(tokens) < 2:
        message_log.append("Get what?")
        return
    target_name = " ".join(tokens[1:]).strip().lower()
    got_item = find_item_recursive_and_remove(current_room["items"], target_name)
    if got_item is None:
        message_log.append(f"You can't find '{target_name}' here.")
        return
    player_inventory.append(got_item)
    message_log.append(f"You pick up the {got_item.get('name', target_name)}.")
    save_player()  # persist

def handle_look_command(tokens):
    if len(tokens) == 1:
        describe_current_room()
        return
    target_name = " ".join(tokens[1:])
    item = find_item_by_name(current_room["items"], target_name)
    if item is None:
        message_log.append(f"You don't see '{target_name}' here.")
        return
    describe_container(item)

def handle_inventory_command():
    if player_inventory:
        message_log.append("You are carrying:")
        for thing in player_inventory:
            nm = thing.get("name", "???")
            ds = thing.get("desc", "").strip()
            if ds:
                message_log.append(f"- {nm}: {ds}")
            else:
                message_log.append(f"- {nm}")
    else:
        message_log.append("You carry nothing.")

def handle_command(cmd: str):
    cmd = cmd.strip()
    if cmd == "":
        return None
    tokens = cmd.lower().split()
    if cmd.lower() in ["quit", "exit"]:
        message_log.append("Game saved. Goodbye.")
        save_player()
        return "QUIT"
    if cmd.lower() in ["inventory", "inv", "i"]:
        handle_inventory_command()
        return None
    if tokens[0] in ["look", "l"]:
        handle_look_command(tokens)
        return None
    if tokens[0] in ["get", "take", "grab"]:
        handle_get_command(tokens)
        return None
    if cmd.lower() in DIRS.keys():
        try_move(cmd.lower())
        return None
    if len(tokens) >= 2 and tokens[0] in ["go", "move", "walk"]:
        direction_word = tokens[1]
        long_to_short = {"north": "n", "northeast": "ne", "east": "e", "southeast": "se",
                         "south": "s", "southwest": "sw", "west": "w", "northwest": "nw"}
        if direction_word in long_to_short:
            direction_word = long_to_short[direction_word]
        if direction_word in DIRS:
            try_move(direction_word)
            return None
    message_log.append(f"You can't '{cmd}'.")
    return None

# -------------------------
# MAIN LOOP
# -------------------------

running = True
load_player()
current_room = load_room(player_x, player_y, player_z)
describe_current_room()

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            save_player()
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                save_player()
                running = False
            elif event.key == pygame.K_BACKSPACE:
                if len(command_input) > 0:
                    command_input = command_input[:-1]
            elif event.key == pygame.K_RETURN:
                message_log.append("> " + command_input)
                result = handle_command(command_input)
                command_input = ""
                if result == "QUIT":
                    running = False
            else:
                if event.unicode and (
                    32 <= ord(event.unicode) <= 126 or ord(event.unicode) >= 160
                ):
                    if len(command_input) < 80:
                        command_input += event.unicode
    render_scene()
    clock.tick(60)

pygame.quit()
sys.exit()
