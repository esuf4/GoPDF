import os
from io import BytesIO
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.slider import Slider
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.graphics import (Color, Line, Rectangle, RoundedRectangle, 
                           StencilPush, StencilUse, StencilUnUse, StencilPop)
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
import fitz  # PyMuPDF

Window.clearcolor = (0.1, 0.1, 0.12, 1)

class ModernButton(Button):
    def __init__(self, radius=10, bg_color=(0.2, 0.2, 0.25, 1), icon_source=None, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = (0, 0, 0, 0)
        self.radius = radius
        self.default_bg = bg_color
        self.icon_img = None
        
        if icon_source and os.path.exists(icon_source):
            self.icon_img = Image(source=icon_source, size_hint=(None, None), size=(dp(28), dp(28)))
            self.add_widget(self.icon_img)
            
        self.bind(pos=self.update_ui, size=self.update_ui)

    def update_ui(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.default_bg)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(self.radius)])
        
        if self.icon_img:
            self.icon_img.center_x = self.x + self.width / 2
            self.icon_img.center_y = self.y + self.height / 2

class PaintCanvas(RelativeLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.line_color = (0, 0.5, 1, 1)
        self.pen_width = dp(2)
        self.eraser_width = dp(30)
        self.drawing_mode = "pen"
        self.doc = None
        self.current_page_idx = 0
        self.total_pages = 0
        self.pages_history = {}

        with self.canvas.before:
            self.paper_color = Color(1, 1, 1, 0)
            self.paper_rect = Rectangle()
            
        self.setup_stencil()
        self.bind(size=self._update_layout, pos=self._update_layout)

    def setup_stencil(self):
        with self.canvas:
            StencilPush()
            self.mask_rect = Rectangle()
            StencilUse()
            self.drawing_group = RelativeLayout()
            self.add_widget(self.drawing_group)
        with self.canvas.after:
            StencilUnUse()
            StencilPop()

    def load_pdf(self, path):
        self.doc = fitz.open(path)
        self.total_pages = len(self.doc)
        self.pages_history = {i: [] for i in range(self.total_pages)}
        self.show_page(0)

    def show_page(self, page_num):
        if not self.doc: return
        self.current_page_idx = page_num
        page = self.doc[page_num]
        pix = page.get_pixmap(dpi=150)
        
        img_data = BytesIO(pix.tobytes("png"))
        core_img = CoreImage(img_data, ext="png")
        self.paper_rect.texture = core_img.texture
        self.paper_color.a = 1
        self.paper_ratio = pix.width / pix.height
        self._update_layout()
        
        self.drawing_group.canvas.clear()
        for instr in self.pages_history[page_num]:
            self.drawing_group.canvas.add(instr['color'])
            self.drawing_group.canvas.add(instr['line'])

    def on_touch_down(self, touch):
        px, py = self.paper_rect.pos
        pw, ph = self.paper_rect.size
        if not (px <= touch.x <= px + pw and py <= touch.y <= py + ph): return False
        
        with self.drawing_group.canvas:
            color_val = self.line_color if self.drawing_mode == "pen" else (1, 1, 1, 1)
            c = Color(*color_val)
            w = self.pen_width if self.drawing_mode == "pen" else self.eraser_width
            l = Line(points=(touch.x, touch.y), width=w, cap='round', joint='round')
            
            touch.ud['line_data'] = {'line': l, 'color': c}
            self.pages_history[self.current_page_idx].append(touch.ud['line_data'])
        return True

    def on_touch_move(self, touch):
        if 'line_data' in touch.ud:
            touch.ud['line_data']['line'].points += [touch.x, touch.y]

    def undo(self):
        history = self.pages_history[self.current_page_idx]
        if history:
            last = history.pop()
            self.drawing_group.canvas.remove(last['color'])
            self.drawing_group.canvas.remove(last['line'])

    def export_pdf(self, output_path):
        if not self.doc: return False
        new_doc = fitz.open(self.doc.name)
        px, py = self.paper_rect.pos
        pw, ph = self.paper_rect.size

        for page_idx, history in self.pages_history.items():
            if not history: continue
            page = new_doc[page_idx]
            pdf_w, pdf_h = page.rect.width, page.rect.height
            
            for item in history:
                pts = item['line'].points
                pdf_pts = []
                for i in range(0, len(pts), 2):
                    rx = (pts[i] - px) / pw
                    ry = 1.0 - ((pts[i+1] - py) / ph)
                    pdf_pts.append([rx * pdf_w, ry * pdf_h])
                
                if len(pdf_pts) > 1:
                    page.draw_polyline(pdf_pts, color=item['color'].rgb, 
                                     width=item['line'].width * (pdf_w / pw))
        new_doc.save(output_path)
        new_doc.close()
        return True

    def _update_layout(self, *args):
        if not hasattr(self, 'paper_ratio'): return
        w, h = self.size
        aw, ah = w * 0.95, h * 0.85
        ratio = self.paper_ratio
        if w/h > ratio:
            ph = ah; pw = ph * ratio
        else:
            pw = aw; ph = pw / ratio
        px, py = (w - pw) / 2, (h - ph) / 2 + dp(35)
        self.paper_rect.pos = self.mask_rect.pos = (px, py)
        self.paper_rect.size = self.mask_rect.size = (pw, ph)

class EditorScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.main_layout = BoxLayout(orientation='horizontal')
        
        # --- Sidebar ---
        self.sidebar_width = dp(75)
        side_bar = BoxLayout(orientation='vertical', size_hint_x=None, width=self.sidebar_width, 
                             spacing=dp(8), padding=[dp(8), dp(15)])
        with side_bar.canvas.before:
            Color(0.08, 0.08, 0.1, 1)
            Rectangle(pos=side_bar.pos, size=(self.sidebar_width, 5000))

        btn_home = ModernButton(icon_source="icons/home.png", height=dp(50), size_hint_y=None, radius=25)
        btn_home.bind(on_release=lambda x: setattr(self.manager, 'current', 'home'))
        
        self.btn_pen = ModernButton(icon_source="icons/pen.png", height=dp(55), size_hint_y=None, bg_color=(0, 0.5, 1, 1))
        self.btn_pen.bind(on_release=lambda x: self.set_mode("pen"))
        
        self.btn_eraser = ModernButton(icon_source="icons/eraser.png", height=dp(55), size_hint_y=None)
        self.btn_eraser.bind(on_release=lambda x: self.set_mode("eraser"))

        # Color Palette
        color_grid = GridLayout(cols=2, spacing=dp(4), size_hint_y=None, height=dp(100))
        palette = [(0,0,0,1), (1,0,0,1), (0,0.7,0,1), (0,0.5,1,1), (1,0.8,0,1), (0.6,0,1,1)]
        for c in palette:
            b = ModernButton(radius=12, bg_color=c, size_hint=(None, None), size=(dp(28), dp(28)))
            b.bind(on_release=lambda x, col=c: self.select_color(col))
            color_grid.add_widget(b)

        # Sliders
        self.slider_area = BoxLayout(orientation='vertical', spacing=dp(5), size_hint_y=None, height=dp(210))
        self.pen_size = self.create_slider_box("P", 1, 40, 2, self.update_pen_size)
        self.era_size = self.create_slider_box("E", 1, 120, 30, self.update_eraser_size)
        self.slider_area.add_widget(self.pen_size)
        self.slider_area.add_widget(self.era_size)

        btn_export = ModernButton(icon_source="icons/save.png", height=dp(50), size_hint_y=None, bg_color=(0, 0.5, 0.3, 1))
        btn_export.bind(on_release=self.confirm_export)

        btn_undo = ModernButton(icon_source="icons/undo.png", height=dp(50), size_hint_y=None)
        btn_undo.bind(on_release=lambda x: self.canvas_area.undo())

        side_bar.add_widget(btn_home)
        side_bar.add_widget(self.btn_pen)
        side_bar.add_widget(self.btn_eraser)
        side_bar.add_widget(color_grid)
        side_bar.add_widget(self.slider_area)
        side_bar.add_widget(btn_export)
        side_bar.add_widget(BoxLayout(size_hint_y=1)) # Spacer
        side_bar.add_widget(btn_undo)

        # --- Workspace ---
        workspace = RelativeLayout()
        self.canvas_area = PaintCanvas()
        page_ctrl = BoxLayout(size_hint=(None, None), size=(dp(200), dp(45)), 
                              pos_hint={'center_x': 0.5, 'y': 0.02}, spacing=dp(5))
        btn_prev = ModernButton(icon_source="icons/chevron_left.png", radius=12)
        btn_prev.bind(on_release=lambda x: self.change_page(-1))
        self.page_label = Label(text="1 / 1", bold=True)
        btn_next = ModernButton(icon_source="icons/chevron_right.png", radius=12)
        btn_next.bind(on_release=lambda x: self.change_page(1))
        
        page_ctrl.add_widget(btn_prev); page_ctrl.add_widget(self.page_label); page_ctrl.add_widget(btn_next)
        workspace.add_widget(self.canvas_area); workspace.add_widget(page_ctrl)

        self.main_layout.add_widget(side_bar); self.main_layout.add_widget(workspace)
        self.add_widget(self.main_layout)

    def create_slider_box(self, t, mn, mx, cur, cb):
        box = BoxLayout(orientation='vertical', spacing=dp(2))
        lbl = Label(text=str(int(cur)), size_hint_y=None, height=dp(18), font_size='10sp', color=(0, 0.6, 1, 1))
        s = Slider(orientation='vertical', min=mn, max=mx, value=cur, value_track=True, value_track_color=(0, 0.5, 1, 1))
        s.bind(value=lambda inst, v: setattr(lbl, 'text', str(int(v))))
        s.bind(value=cb)
        box.add_widget(lbl); box.add_widget(s)
        return box

    def update_pen_size(self, i, v): self.canvas_area.pen_width = dp(v)
    def update_eraser_size(self, i, v): self.canvas_area.eraser_width = dp(v)
    def select_color(self, c): self.canvas_area.line_color = c; self.set_mode("pen")

    def set_mode(self, m):
        self.canvas_area.drawing_mode = m
        self.btn_pen.default_bg = (0, 0.5, 1, 1) if m == "pen" else (0.2, 0.2, 0.25, 1)
        self.btn_eraser.default_bg = (0, 0.5, 1, 1) if m == "eraser" else (0.2, 0.2, 0.25, 1)
        self.btn_pen.update_ui(); self.btn_eraser.update_ui()

    def change_page(self, d):
        idx = self.canvas_area.current_page_idx + d
        if 0 <= idx < self.canvas_area.total_pages:
            self.canvas_area.show_page(idx)
            self.page_label.text = f"{idx + 1} / {self.canvas_area.total_pages}"

    def confirm_export(self, instance):
        if not self.canvas_area.doc: return
        out = self.canvas_area.doc.name.replace(".pdf", "_edited.pdf")
        if self.canvas_area.export_pdf(out):
            content = Label(text=f"Saved:\n{os.path.basename(out)}")
            Popup(title='Success', content=content, size_hint=(None, None), size=(dp(250), dp(150))).open()

class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        l = BoxLayout(orientation='vertical', padding=dp(80), spacing=dp(30))
        l.add_widget(Label(text="GoPDF", font_size='70sp', bold=True, color=(0, 0.6, 1, 1)))
        btn = ModernButton(text="Open PDF", size_hint=(None, None), size=(dp(250), dp(60)), 
                           pos_hint={'center_x': .5}, bg_color=(0, 0.5, 1, 1), radius=30)
        btn.bind(on_release=self.open_pdf)
        l.add_widget(btn); self.add_widget(l)

    def open_pdf(self, inst):
        from plyer import filechooser
        filechooser.open_file(on_selection=self.handle_selection)

    def handle_selection(self, selection):
        if selection:
            self.manager.current = 'editor'
            ed = self.manager.get_screen('editor')
            Clock.schedule_once(lambda dt: ed.canvas_area.load_pdf(selection[0]), 0.2)
            Clock.schedule_once(lambda dt: setattr(ed.page_label, 'text', f"1 / {ed.canvas_area.total_pages}"), 0.4)

class GoPDFApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(HomeScreen(name='home'))
        sm.add_widget(EditorScreen(name='editor'))
        return sm

if __name__ == '__main__':
    GoPDFApp().run()