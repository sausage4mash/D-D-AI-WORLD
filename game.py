import pygame
import sys
import math
import os
import json
import subprocess
from datetime import datetime

# Windows-only beep
try:
    import winsound
    def beep():
        winsound.Beep(880, 80)
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
WARN = (200, 80, 80)
INPUT_BG = (50, 58, 75)
INPUT_BORDER = (110, 120, 140)
INPUT_ACTIVE_BORDER = (120, 200, 255)

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

# --- Items state ---
items = []  # list of {"name":str,"desc":str,"contains":[...]}
adding_mode = False
adding_parent_path = []
new_item_name = ""
new_item_desc = ""
active_field = None

# --- Scroll state for left column ---
scroll_offset = 0  # shifts whole left column up/down


def pad(n: int) -> str:
    return f"-{abs(n):02d}" if n < 0 else f"{n:02d}"


def coords_filename():
    folder = "world_tiles"
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{pad(x)}-{pad(y)}-{pad(z)}.json")


def get_item_by_path(path):
    ref_list = items
    current_item = None
    for depth, idx in enumerate(path):
        if not isinstance(ref_list, list):
            return None
        if idx < 0 or idx >= len(ref_list):
            return None
        current_item = ref_list[idx]
        if depth < len(path) - 1:
            if "contains" not in current_item or not isinstance(current_item["contains"], list):
                return None
            ref_list = current_item["contains"]
    return current_item


def add_item_under_path(parent_path, name, desc):
    name = name.strip()
    if not name:
        return False
    new_obj = {
        "name": name,
        "desc": desc.strip(),
        "contains": []
    }
    if parent_path == []:
        items.append(new_obj)
        return True
    parent = get_item_by_path(parent_path)
    if not parent:
        return False
    if "contains" not in parent or not isinstance(parent["contains"], list):
        parent["contains"] = []
    parent["contains"].append(new_obj)
    return True


def flatten_items_for_display(item_list, base_path, level, out):
    for i, it in enumerate(item_list):
        path = base_path + [i]
        nm = it.get("name", "(no name)")
        ds = it.get("desc", "").strip()
        indent = "  " * level
        if ds:
            line_text = f"{indent}- {nm}: {ds}"
        else:
            line_text = f"{indent}- {nm}"
        out.append({
            "text": line_text,
            "path": path,
            "plus_rect": None,
        })
        kids = it.get("contains", [])
        if isinstance(kids, list) and kids:
            flatten_items_for_display(kids, path, level+1, out)


def load_tile():
    global exits, description_text, last_move
    global save_message, save_message_ticks
    global items

    path = coords_filename()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            loaded_exits = data.get("exits", {})
            exits_new = {d: bool(loaded_exits.get(d, False)) for d in EXIT_ORDER}
            exits.clear()
            exits.update(exits_new)

            description_text = str(data.get("description", ""))
            last_move = data.get("last_move")

            items_loaded = data.get("items", [])
            if not isinstance(items_loaded, list):
                items_loaded = []
            items[:] = items_loaded

            save_message = f"Loaded from {path}"
            save_message_ticks = 120
        except Exception as e:
            for k in EXIT_ORDER:
                exits[k] = False
            description_text = ""
            items[:] = []
            save_message = f"Load error: {e}"
            save_message_ticks = 180
    else:
        for k in EXIT_ORDER:
            exits[k] = False
        description_text = ""
        last_move = None
        items[:] = []
        save_message = "New room (no file yet)"
        save_message_ticks = 90


def draw_button(text, center, mouse_pos, *,
                fill_color=CYAN, hover_color=HOVER,
                padding=(30,16), radius=15,
                font=font_btn, disabled=False):
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
        hit_rects[name] = pygame.Rect(
            bx - btn_radius, by - btn_radius,
            btn_radius*2, btn_radius*2
        )

    pygame.draw.circle(screen, GREY, center, 6)
    return hit_rects


def move_vector(name):
    for nm, _, delta in DIRS:
        if nm == name:
            return delta
    return (0, 0, 0)


def apply_move(name):
    global x, y, z, last_move, pending_move
    dx, dy, dz = move_vector(name)
    x += dx
    y += dy
    z += dz
    last_move = name
    pending_move = None
    load_tile()


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
        "items": items,
        "saved_at": datetime.utcnow().isoformat() + "Z",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    save_message = f"Saved to {path}"
    save_message_ticks = 120


def draw_room_editor(x0, y0):
    panel_w, panel_h = 260, 240
    rect_panel = pygame.Rect(x0, y0, panel_w, panel_h)

    pygame.draw.rect(screen, BOX, rect_panel, border_radius=12)
    pygame.draw.rect(screen, GREY, rect_panel, width=2, border_radius=12)
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
                pygame.draw.line(screen, WHITE, (cx+4, cy+10),
                                 (cx+9, cy+15), 2)
                pygame.draw.line(screen, WHITE, (cx+9, cy+15),
                                 (cx+16, cy+5), 2)
            lab = font_tiny.render(d, True, WHITE)
            screen.blit(lab, (cx + box_size + 8, cy - 2))
            hit[d] = rect
    return hit, rect_panel


def draw_description_box(x0, y0, w, h):
    global caret_visible, caret_timer
    panel_rect = pygame.Rect(x0, y0, w, h)

    focused_col = (120, 200, 255) if desc_active else GREY
    pygame.draw.rect(screen, BOX, panel_rect, border_radius=12)
    pygame.draw.rect(screen, focused_col, panel_rect, width=2, border_radius=12)
    label = font_small.render("Description", True, WHITE)
    screen.blit(label, (x0 + 12, y0 + 8))

    inner = pygame.Rect(x0 + 12, y0 + 40, w - 24, h - 52)
    pygame.draw.rect(screen, INPUT_BG, inner, border_radius=8)
    pygame.draw.rect(screen, INPUT_BORDER, inner, width=1, border_radius=8)

    lines = wrap_text(description_text, font_tiny, inner.w - 10)
    y_cursor = inner.y + 6
    for line in lines[-200:]:
        img = font_tiny.render(line, True, WHITE)
        screen.blit(img, (inner.x + 6, y_cursor))
        y_cursor += img.get_height() + 2

    caret_timer += clock.get_time()
    if caret_timer >= 500:
        caret_visible = not caret_visible
        caret_timer = 0

    if desc_active and caret_visible:
        last_line = lines[-1] if lines else ""
        caret_x = inner.x + 6 + font_tiny.size(last_line)[0]
        caret_y = inner.y + 6 + (len(lines)-1) * (font_tiny.get_height() + 2)
        pygame.draw.line(
            screen, WHITE,
            (caret_x, caret_y),
            (caret_x, caret_y + font_tiny.get_height()),
            1
        )

    update_center = (x0 + w//2, y0 + h + 30)
    update_rect = draw_button(
        "Update", update_center, pygame.mouse.get_pos(),
        fill_color=CYAN, hover_color=HOVER,
        padding=(20,10), radius=10, font=font_tiny
    )

    return panel_rect, update_rect


def draw_items_panel(x0, y0, w, h):
    panel_rect = pygame.Rect(x0, y0, w, h)
    pygame.draw.rect(screen, BOX, panel_rect, border_radius=12)
    pygame.draw.rect(screen, GREY, panel_rect, width=2, border_radius=12)

    title = font_small.render("Items", True, WHITE)
    screen.blit(title, (x0 + 12, y0 + 10))

    new_top_btn = pygame.Rect(x0 + w - 140, y0 + 8, 120, 28)
    mouse_pos = pygame.mouse.get_pos()
    hov_top = new_top_btn.collidepoint(mouse_pos)
    pygame.draw.rect(screen, CYAN if hov_top else HOVER, new_top_btn, border_radius=6)
    txt_new = font_tiny.render("+ New Item", True, INK_DARK)
    screen.blit(txt_new, txt_new.get_rect(center=new_top_btn.center))

    list_rect = pygame.Rect(x0 + 12, y0 + 48, w - 24, h - 60)
    pygame.draw.rect(screen, INPUT_BG, list_rect, border_radius=6)
    pygame.draw.rect(screen, INPUT_BORDER, list_rect, width=1, border_radius=6)

    flat = []
    flatten_items_for_display(items, [], 0, flat)

    plus_buttons = []
    row_y = list_rect.y + 6
    row_x = list_rect.x + 6
    row_h = font_tiny.get_height() + 8

    for row in flat:
        label_text = row["text"]
        path = row["path"]

        txt_img = font_tiny.render(label_text, True, WHITE)
        screen.blit(txt_img, (row_x, row_y))

        plus_rect = pygame.Rect(
            row_x + txt_img.get_width() + 10,
            row_y,
            28,
            22
        )
        row["plus_rect"] = plus_rect
        hov_plus = plus_rect.collidepoint(mouse_pos)
        pygame.draw.rect(screen, CYAN if hov_plus else HOVER, plus_rect, border_radius=4)
        plus_label = font_tiny.render("+", True, INK_DARK)
        screen.blit(plus_label, plus_label.get_rect(center=plus_rect.center))

        plus_buttons.append((plus_rect, path))

        row_y += row_h
        if row_y > list_rect.bottom - row_h:
            break

    popup_info = None
    if adding_mode:
        popup_w = w - 40
        popup_h = 160
        popup_x = x0 + 20
        popup_y = y0 + h//2 - popup_h//2
        popup_rect = pygame.Rect(popup_x, popup_y, popup_w, popup_h)

        pygame.draw.rect(screen, BOX, popup_rect, border_radius=12)
        pygame.draw.rect(screen, CYAN, popup_rect, width=2, border_radius=12)

        ttl = font_small.render("Add Item", True, WHITE)
        screen.blit(ttl, (popup_x + 12, popup_y + 8))

        name_label = font_tiny.render("Name:", True, GREY)
        screen.blit(name_label, (popup_x + 12, popup_y + 40))
        name_rect = pygame.Rect(popup_x + 80, popup_y + 36, popup_w - 92, 26)
        pygame.draw.rect(screen, INPUT_BG, name_rect, border_radius=6)
        pygame.draw.rect(
            screen,
            INPUT_ACTIVE_BORDER if active_field == "name" else INPUT_BORDER,
            name_rect, width=1, border_radius=6
        )
        name_img = font_tiny.render(new_item_name, True, WHITE)
        screen.blit(name_img, (name_rect.x + 6, name_rect.y + 4))

        desc_label = font_tiny.render("Desc:", True, GREY)
        screen.blit(desc_label, (popup_x + 12, popup_y + 74))
        desc_rect = pygame.Rect(popup_x + 80, popup_y + 70, popup_w - 92, 40)
        pygame.draw.rect(screen, INPUT_BG, desc_rect, border_radius=6)
        pygame.draw.rect(
            screen,
            INPUT_ACTIVE_BORDER if active_field == "desc" else INPUT_BORDER,
            desc_rect, width=1, border_radius=6
        )

        d_lines = wrap_text(new_item_desc, font_tiny, desc_rect.w - 10)
        line_y = desc_rect.y + 4
        for ln in d_lines[:3]:
            img = font_tiny.render(ln, True, WHITE)
            screen.blit(img, (desc_rect.x + 6, line_y))
            line_y += font_tiny.get_height() + 2

        add_btn = pygame.Rect(popup_x + popup_w - 180, popup_y + popup_h - 40, 80, 28)
        cancel_btn = pygame.Rect(popup_x + popup_w - 90, popup_y + popup_h - 40, 80, 28)

        for rct, lbl in [(add_btn, "Add"), (cancel_btn, "Cancel")]:
            hov = rct.collidepoint(mouse_pos)
            pygame.draw.rect(screen, CYAN if hov else HOVER, rct, border_radius=6)
            txt = font_tiny.render(lbl, True, INK_DARK)
            screen.blit(txt, txt.get_rect(center=rct.center))

        popup_info = {
            "popup_rect": popup_rect,
            "name_rect": name_rect,
            "desc_rect": desc_rect,
            "add_btn": add_btn,
            "cancel_btn": cancel_btn,
        }

    return {
        "panel_rect": panel_rect,
        "new_top_btn": new_top_btn,
        "plus_buttons": plus_buttons,
        "popup": popup_info,
    }


def shifted(rect, dy):
    return pygame.Rect(rect.x, rect.y + dy, rect.w, rect.h)


# --- Main loop ---
running = True
prev_mouse_pressed = False

while running:
    mouse_pos_raw = pygame.mouse.get_pos()
    mouse_pressed = pygame.mouse.get_pressed()[0]
    clicked_this_frame = mouse_pressed and not prev_mouse_pressed

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEWHEEL and current_screen == "map_builder":
            scroll_offset += event.y * 40
            if scroll_offset > 0:
                scroll_offset = 0

        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                running = False

            elif current_screen == "map_builder":
                # typing into room description (only if it's active AND not in item popup)
                if desc_active and not adding_mode:
                    if event.key == pygame.K_BACKSPACE:
                        if description_text:
                            description_text = description_text[:-1]
                        continue
                    elif event.key == pygame.K_RETURN:
                        description_text += "\n"
                        continue
                    else:
                        if event.unicode and (
                            32 <= ord(event.unicode) <= 126 or ord(event.unicode) >= 160
                        ):
                            if len(description_text) < 2000:
                                description_text += event.unicode
                            continue

                # typing into popup (adding item)
                if adding_mode:
                    if active_field == "name":
                        if event.key == pygame.K_BACKSPACE:
                            if new_item_name:
                                new_item_name = new_item_name[:-1]
                            continue
                        elif event.key == pygame.K_RETURN:
                            active_field = "desc"
                            continue
                        else:
                            if event.unicode and (
                                32 <= ord(event.unicode) <= 126 or ord(event.unicode) >= 160
                            ):
                                if len(new_item_name) < 60:
                                    new_item_name += event.unicode
                                continue

                    elif active_field == "desc":
                        if event.key == pygame.K_BACKSPACE:
                            if new_item_desc:
                                new_item_desc = new_item_desc[:-1]
                            continue
                        elif event.key == pygame.K_RETURN:
                            if len(new_item_desc) < 2000:
                                new_item_desc += "\n"
                            continue
                        else:
                            if event.unicode and (
                                32 <= ord(event.unicode) <= 126 or ord(event.unicode) >= 160
                            ):
                                if len(new_item_desc) < 2000:
                                    new_item_desc += event.unicode
                                continue

    screen.fill(BG)

    # ========== MENU SCREEN ==========
    if current_screen == "menu":
        title = font_big.render("Cog World", True, CYAN)
        screen.blit(title, title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 80)))

        play_rect_main = draw_button(
            "The Game Cog World",
            (WIDTH // 2, HEIGHT // 2 + 10),
            mouse_pos_raw
        )
        if clicked_this_frame and play_rect_main.collidepoint(mouse_pos_raw):
            subprocess.Popen([sys.executable, "game-main.py"])
            pygame.quit()
            sys.exit()

        play_rect_builder = draw_button(
            "Map Builder",
            (WIDTH // 2, HEIGHT // 2 + 80),
            mouse_pos_raw
        )
        if clicked_this_frame and play_rect_builder.collidepoint(mouse_pos_raw):
            current_screen = "map_builder"
            load_tile()

        tip = font_small.render("Press ESC or Q to exit", True, GREY)
        screen.blit(tip, tip.get_rect(center=(WIDTH // 2, HEIGHT - 60)))

    # ========== MAP BUILDER SCREEN ==========
    elif current_screen == "map_builder":
        title = font_big.render("Map Builder", True, CYAN)
        screen.blit(title, (40, 30))

        back_rect = draw_button(
            "Back",
            (WIDTH - 120, 50),
            mouse_pos_raw,
            fill_color=CYAN,
            hover_color=HOVER,
            padding=(24, 10),
            font=font_small
        )
        if clicked_this_frame and back_rect.collidepoint(mouse_pos_raw):
            current_screen = "menu"
            desc_active = False
            adding_mode = False
            active_field = None

        coords_text = f"Coords: (x={x}, y={y}, z={z})"
        screen.blit(font_small.render(coords_text, True, OK), (40, 150))

        status = (
            f"Pending: {pending_move} (press Next to confirm)"
            if pending_move else
            "Click a direction"
        )
        screen.blit(font_small.render(status, True, GREY), (320, 200))

        scroll_hint = "Mouse wheel to scroll list"
        screen.blit(font_tiny.render(scroll_hint, True, GREY), (40, 180))

        # SCROLL COLUMN positions
        y_room   = 200 + scroll_offset
        # dynamic height for description
        max_width = 260 - 24
        lines = wrap_text(description_text, font_tiny, max_width)
        line_h = font_tiny.get_height() + 2
        needed_h = 40 + len(lines) * line_h + 20
        desc_h = max(220, min(needed_h, 420))

        y_desc   = 460 + scroll_offset
        y_items  = y_desc + desc_h + 70  # push items down after bigger desc

        editor_hit, editor_rect = draw_room_editor(40, y_room)
        desc_panel_rect, update_rect = draw_description_box(40, y_desc, 260, desc_h)
        items_panel_obj = draw_items_panel(40, y_items, 260, 260)

        # Compass (fixed)
        compass_center = (WIDTH // 2 + 120, HEIGHT // 2 + 40)
        hit_rects = draw_compass(compass_center, 140, mouse_pos_raw)

        # handle clicks in scroll column
        if clicked_this_frame:
            if adding_mode and items_panel_obj["popup"]:
                pop = items_panel_obj["popup"]
                if shifted(pop["name_rect"], -scroll_offset).collidepoint(mouse_pos_raw):
                    active_field = "name"
                    beep()

                elif shifted(pop["desc_rect"], -scroll_offset).collidepoint(mouse_pos_raw):
                    active_field = "desc"
                    beep()

                elif shifted(pop["add_btn"], -scroll_offset).collidepoint(mouse_pos_raw):
                    ok = add_item_under_path(
                        adding_parent_path,
                        new_item_name,
                        new_item_desc
                    )
                    if ok:
                        beep()
                    adding_mode = False
                    active_field = None
                    new_item_name = ""
                    new_item_desc = ""
                    adding_parent_path = []

                elif shifted(pop["cancel_btn"], -scroll_offset).collidepoint(mouse_pos_raw):
                    beep()
                    adding_mode = False
                    active_field = None
                    new_item_name = ""
                    new_item_desc = ""
                    adding_parent_path = []
            else:
                if shifted(desc_panel_rect, -scroll_offset).collidepoint(mouse_pos_raw):
                    if not desc_active:
                        beep()
                    desc_active = True
                    adding_mode = False
                    active_field = None

                elif shifted(update_rect, -scroll_offset).collidepoint(mouse_pos_raw):
                    save_tile()
                    beep()

                else:
                    did_click_exit = False
                    for d, r in editor_hit.items():
                        if shifted(r, -scroll_offset).collidepoint(mouse_pos_raw):
                            exits[d] = not exits[d]
                            beep()
                            did_click_exit = True
                            break

                    if not did_click_exit:
                        if shifted(items_panel_obj["new_top_btn"], -scroll_offset).collidepoint(mouse_pos_raw):
                            beep()
                            adding_mode = True
                            adding_parent_path = []
                            new_item_name = ""
                            new_item_desc = ""
                            active_field = "name"
                            desc_active = False

                        else:
                            clicked_plus = False
                            for pr, path in items_panel_obj["plus_buttons"]:
                                if shifted(pr, -scroll_offset).collidepoint(mouse_pos_raw):
                                    beep()
                                    adding_mode = True
                                    adding_parent_path = path[:]
                                    new_item_name = ""
                                    new_item_desc = ""
                                    active_field = "name"
                                    desc_active = False
                                    clicked_plus = True
                                    break

                            if not clicked_plus:
                                desc_active = False
                                active_field = None

                # Compass (fixed, no scroll)
                for name, r in hit_rects.items():
                    if r.collidepoint(mouse_pos_raw):
                        pending_move = name
                        beep()
                        break

        # Bottom row buttons (fixed)
        row_y = HEIGHT - 110
        next_rect = draw_button(
            "Next",
            (WIDTH // 2 - 260, row_y),
            mouse_pos_raw,
            disabled=(pending_move is None)
        )
        cancel_rect = draw_button(
            "Cancel",
            (WIDTH // 2, row_y),
            mouse_pos_raw,
            fill_color=(150,150,150),
            hover_color=(180,180,180),
            padding=(30,16),
            font=font_btn,
            disabled=(pending_move is None)
        )
        save_rect = draw_button(
            "Save JSON",
            (WIDTH // 2 + 260, row_y),
            mouse_pos_raw
        )

        if clicked_this_frame and pending_move and next_rect.collidepoint(mouse_pos_raw):
            apply_move(pending_move)

        if clicked_this_frame and pending_move and cancel_rect.collidepoint(mouse_pos_raw):
            pending_move = None

        if clicked_this_frame and save_rect.collidepoint(mouse_pos_raw):
            save_tile()
            beep()

        if save_message and save_message_ticks > 0:
            color_for_toast = OK
            if save_message.startswith("Load error"):
                color_for_toast = WARN
            toast = font_small.render(save_message, True, color_for_toast)
            screen.blit(toast, toast.get_rect(center=(WIDTH // 2, HEIGHT - 170)))
            save_message_ticks -= 1

    pygame.display.flip()
    dt = clock.tick(60)
    prev_mouse_pressed = mouse_pressed

pygame.quit()
sys.exit()
