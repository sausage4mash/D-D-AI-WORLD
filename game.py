import pygame
import sys
import math
import os
import json
from datetime import datetime

# Windows-only beep (safe no-op elsewhere)
try:
    import winsound
    def beep():
        winsound.Beep(880, 80)  # freq Hz, duration ms
except Exception:
    def beep():
        pass

pygame.init()
info = pygame.display.Info()
WIDTH, HEIGHT = info.current_w, info.current_h

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Cog World")

# --- Colours ---
BG = (15, 20, 30)
CYAN = (0, 255, 255)
GREY = (180, 180, 180)
HOVER = (100, 255, 255)
INK_DARK = (15, 20, 30)
OK = (52, 211, 153)
BOX = (70, 80, 100)
WHITE = (235, 235, 235)

# --- Fonts ---
font_big = pygame.font.SysFont(None, 100)
font_btn = pygame.font.SysFont(None, 60)
font_small = pygame.font.SysFont(None, 40)
font_tiny = pygame.font.SysFont(None, 26)

clock = pygame.time.Clock()
current_screen = "menu"  # 'menu' or 'map_builder'

# --- World state ---
x, y, z = 0, 0, 0
last_move = None
pending_move = None
save_message = None
save_message_ticks = 0

# --- Room editor state ---
EXIT_ORDER = ["n", "ne", "e", "se", "s", "sw", "w", "nw"]
exits = {d: False for d in EXIT_ORDER}
description_text = ""
desc_active = False
caret_visible = True
caret_timer = 0

def pad(n: int) -> str:
    return f"-{abs(n):02d}" if n < 0 else f"{n:02d}"

def coords_filename():
    folder = "world_tiles"
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{pad(x)}-{pad(y)}-{pad(z)}.json")

def load_tile():
    """Load exits/description/last_move from current coords file, or reset if none."""
    global exits, description_text, last_move, save_message, save_message_ticks
    path = coords_filename()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # keep a complete set of exits keys
            loaded_exits = data.get("exits", {})
            exits = {d: bool(loaded_exits.get(d, False)) for d in EXIT_ORDER}
            description_text = str(data.get("description", ""))
            last_move = data.get("last_move")
            save_message = f"Loaded from {path}"
            save_message_ticks = 120
        except Exception as e:
            # on read/parse error, reset cleanly
            exits = {d: False for d in EXIT_ORDER}
            description_text = ""
            save_message = f"Load error: {e}"
            save_message_ticks = 180
    else:
        exits = {d: False for d in EXIT_ORDER}
        description_text = ""
        last_move = None
        save_message = "New room (no file yet)"
        save_message_ticks = 90

# --- Button helper (edge-click support external) ---
def draw_button(text, center, mouse_pos, *, fill_color=CYAN, hover_color=HOVER,
                padding=(30, 16), radius=15, font=font_btn, disabled=False):
    label_color = INK_DARK if not disabled else (60, 60, 60)
    label = font.render(text, True, label_color)
    rect = label.get_rect(center=center).inflate(*padding)
    base = (120, 120, 120) if disabled else fill_color
    color = base
    if rect.collidepoint(mouse_pos) and not disabled:
        color = hover_color
    pygame.draw.rect(screen, color, rect, border_radius=radius)
    screen.blit(label, label.get_rect(center=rect.center))
    return rect

# --- Compass helper ---
DIRS = [
    ("n",  90,  (0, +1, 0)),
    ("ne", 45,  (+1, +1, 0)),
    ("e",   0,  (+1, 0, 0)),
    ("se", -45, (+1, -1, 0)),
    ("s",  -90, (0, -1, 0)),
    ("sw", -135,(-1, -1, 0)),
    ("w",  180, (-1, 0, 0)),
    ("nw", 135, (-1, +1, 0)),
]

def draw_compass(center, radius, mouse_pos):
    cx, cy = center
    hit_rects = {}
    pygame.draw.circle(screen, GREY, center, radius, width=2)

    for name, deg, _ in DIRS:
        rad = math.radians(deg)
        bx = cx + int(radius * math.cos(rad))
        by = cy - int(radius * math.sin(rad))
        btn_radius = 34
        hovered = (mouse_pos[0]-bx)**2 + (mouse_pos[1]-by)**2 <= btn_radius**2
        pygame.draw.circle(screen, HOVER if hovered else CYAN, (bx, by), btn_radius)
        label = font_small.render(name, True, INK_DARK)
        screen.blit(label, label.get_rect(center=(bx, by)))
        hit_rects[name] = pygame.Rect(bx - btn_radius, by - btn_radius, btn_radius*2, btn_radius*2)

    pygame.draw.circle(screen, GREY, center, 6)
    return hit_rects

def move_vector(name):
    for nm, _, delta in DIRS:
        if nm == name:
            return delta
    return (0, 0, 0)

def apply_move(name):
    """Apply pending move to (x,y,z) and then load that room's JSON if present."""
    global x, y, z, last_move, pending_move
    dx, dy, dz = move_vector(name)
    x += dx; y += dy; z += dz
    last_move = name
    pending_move = None
    load_tile()  # <-- auto-load data for the new room

# --- Text wrapping for description box ---
def wrap_text(text, font, max_width):
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        line = ""
        for w in words:
            test = (line + " " + w).strip() if line else w
            if font.size(test)[0] <= max_width:
                line = test
            else:
                if line:
                    lines.append(line)
                while font.size(w)[0] > max_width and len(w) > 1:
                    cut = len(w)
                    while cut > 1 and font.size(w[:cut])[0] > max_width:
                        cut -= 1
                    lines.append(w[:cut])
                    w = w[cut:]
                line = w
        lines.append(line)
    return lines

def save_tile():
    global save_message, save_message_ticks
    path = coords_filename()
    data = {
        "coords": {"x": x, "y": y, "z": z},
        "last_move": last_move,
        "exits": exits,
        "description": description_text,
        "saved_at": datetime.utcnow().isoformat() + "Z",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    save_message = f"Saved to {path}"
    save_message_ticks = 120  # ~2s

# --- Room editor (checkbox list) ---
def draw_room_editor(x0, y0, mouse_pos):
    panel_w, panel_h = 260, 240
    pygame.draw.rect(screen, BOX, (x0, y0, panel_w, panel_h), border_radius=12)
    pygame.draw.rect(screen, GREY, (x0, y0, panel_w, panel_h), width=2, border_radius=12)
    title = font_small.render("Room Editor", True, WHITE)
    screen.blit(title, (x0 + 12, y0 + 10))
    sub = font_tiny.render("Exits (tick to allow):", True, GREY)
    screen.blit(sub, (x0 + 12, y0 + 48))

    hit = {}
    col1_x = x0 + 16
    col2_x = x0 + 140
    start_y = y0 + 80
    step_y = 32
    box_size = 20

    pairs = [("n","ne"), ("e","se"), ("s","sw"), ("w","nw")]
    for i, (d1, d2) in enumerate(pairs):
        for j, d in enumerate((d1, d2)):
            cx = col1_x if j == 0 else col2_x
            cy = start_y + i * step_y
            rect = pygame.Rect(cx, cy, box_size, box_size)
            pygame.draw.rect(screen, WHITE, rect, width=2, border_radius=4)
            if exits[d]:
                pygame.draw.line(screen, WHITE, (cx+4, cy+10), (cx+9, cy+15), 2)
                pygame.draw.line(screen, WHITE, (cx+9, cy+15), (cx+16, cy+5), 2)
            lab = font_tiny.render(d, True, WHITE)
            screen.blit(lab, (cx + box_size + 8, cy - 2))
            hit[d] = rect
    return hit

# --- Description box (below editor) ---
def draw_description_box(x0, y0, w, h, mouse_pos):
    global caret_visible, caret_timer
    focused_col = (120, 200, 255) if desc_active else GREY
    pygame.draw.rect(screen, BOX, (x0, y0, w, h), border_radius=12)
    pygame.draw.rect(screen, focused_col, (x0, y0, w, h), width=2, border_radius=12)
    label = font_small.render("Description", True, WHITE)
    screen.blit(label, (x0 + 12, y0 + 8))

    inner = pygame.Rect(x0 + 12, y0 + 40, w - 24, h - 52)
    pygame.draw.rect(screen, (50, 58, 75), inner, border_radius=8)
    pygame.draw.rect(screen, (110, 120, 140), inner, width=1, border_radius=8)

    lines = wrap_text(description_text, font_tiny, inner.w - 10)
    y = inner.y + 6
    for line in lines[-200:]:
        img = font_tiny.render(line, True, WHITE)
        screen.blit(img, (inner.x + 6, y))
        y += img.get_height() + 2

    caret_timer += clock.get_time()
    if caret_timer >= 500:
        caret_visible = not caret_visible
        caret_timer = 0

    if desc_active and caret_visible:
        last_line = lines[-1] if lines else ""
        caret_x = inner.x + 6 + font_tiny.size(last_line)[0]
        caret_y = inner.y + 6 + (len(lines)-1) * (font_tiny.get_height() + 2)
        pygame.draw.line(screen, WHITE, (caret_x, caret_y), (caret_x, caret_y + font_tiny.get_height()), 1)

    return pygame.Rect(x0, y0, w, h), inner

# --- Main loop ---
running = True
prev_mouse_pressed = False  # for edge-clicks

while running:
    mouse_pos = pygame.mouse.get_pos()
    mouse_pressed = pygame.mouse.get_pressed()[0]
    clicked_this_frame = mouse_pressed and not prev_mouse_pressed  # edge

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                running = False
            elif current_screen == "map_builder" and desc_active:
                if event.key == pygame.K_BACKSPACE:
                    if description_text:
                        description_text = description_text[:-1]
                elif event.key == pygame.K_RETURN:
                    description_text += "\n"
                else:
                    if event.unicode and (32 <= ord(event.unicode) <= 126 or ord(event.unicode) >= 160):
                        if len(description_text) < 2000:
                            description_text += event.unicode

    screen.fill(BG)

    if current_screen == "menu":
        title = font_big.render("Cog World", True, CYAN)
        screen.blit(title, title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 80)))

        play_rect = draw_button("Map Builder", (WIDTH // 2, HEIGHT // 2 + 80), mouse_pos)
        if clicked_this_frame and play_rect.collidepoint(mouse_pos):
            current_screen = "map_builder"
            load_tile()  # <-- load data for (0,0,0) or current coords on entry

        tip = font_small.render("Press ESC or Q to exit", True, GREY)
        screen.blit(tip, tip.get_rect(center=(WIDTH // 2, HEIGHT - 60)))

    elif current_screen == "map_builder":
        # Header
        title = font_big.render("Map Builder", True, CYAN)
        screen.blit(title, (40, 30))

        # Back
        back_rect = draw_button("Back", (WIDTH - 120, 50), mouse_pos, fill_color=CYAN, hover_color=HOVER,
                                padding=(24, 10), font=font_small)
        if clicked_this_frame and back_rect.collidepoint(mouse_pos):
            current_screen = "menu"
            desc_active = False

        # Room editor (left)
        editor_hit = draw_room_editor(40, 200, mouse_pos)
        if clicked_this_frame:
            for d, r in editor_hit.items():
                if r.collidepoint(mouse_pos):
                    exits[d] = not exits[d]
                    beep()
                    break

        # Description box (left, under editor)
        desc_panel_rect, _ = draw_description_box(40, 460, 260, 220, mouse_pos)
        if clicked_this_frame:
            if desc_panel_rect.collidepoint(mouse_pos):
                if not desc_active:
                    beep()
                desc_active = True
            else:
                desc_active = False

        # Coords + status
        coords_text = f"Coords: (x={x}, y={y}, z={z})"
        screen.blit(font_small.render(coords_text, True, OK), (40, 150))

        status = f"Pending: {pending_move} (press Next to confirm)" if pending_move else "Click a direction"
        screen.blit(font_small.render(status, True, GREY), (320, 200))

        # Compass (center-right)
        compass_center = (WIDTH // 2 + 120, HEIGHT // 2 + 40)
        hit_rects = draw_compass(compass_center, 140, mouse_pos)

        # Compass click -> set pending + beep
        if clicked_this_frame:
            for name, r in hit_rects.items():
                if r.collidepoint(mouse_pos):
                    pending_move = name
                    beep()
                    break

        # Bottom action row
        row_y = HEIGHT - 110
        next_rect   = draw_button("Next",     (WIDTH // 2 - 260, row_y), mouse_pos,
                                  disabled=(pending_move is None))
        cancel_rect = draw_button("Cancel",   (WIDTH // 2,         row_y), mouse_pos,
                                  fill_color=(150,150,150), hover_color=(180,180,180),
                                  disabled=(pending_move is None))
        save_rect   = draw_button("Save JSON",(WIDTH // 2 + 260,   row_y), mouse_pos)

        if clicked_this_frame and pending_move and next_rect.collidepoint(mouse_pos):
            apply_move(pending_move)

        if clicked_this_frame and pending_move and cancel_rect.collidepoint(mouse_pos):
            pending_move = None

        if clicked_this_frame and save_rect.collidepoint(mouse_pos):
            save_tile()

        # Save/Load toast
        if save_message and save_message_ticks > 0:
            toast = font_small.render(save_message, True, OK)
            screen.blit(toast, toast.get_rect(center=(WIDTH // 2, HEIGHT - 170)))
            save_message_ticks -= 1

    pygame.display.flip()
    dt = clock.tick(60)
    prev_mouse_pressed = mouse_pressed

pygame.quit()
sys.exit()
