"""
Baixador de MP3 - interface gráfica para o yt-dlp (tema escuro)
Empacotado com PyInstaller (ver build.bat): leva yt-dlp, FFmpeg e Deno embutidos.
"""
import os
import re
import sys
import queue
import shutil
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from tkinter import filedialog, messagebox

import customtkinter as ctk
import yt_dlp
from yt_dlp.utils import DownloadCancelled


def recurso(relativo):
    """Caminho de um arquivo embutido (funciona no .exe e rodando o .py)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relativo)


# Coloca o ffmpeg.exe e o deno.exe embutidos no PATH do processo
_BIN = recurso("bin")
if os.path.isdir(_BIN):
    os.environ["PATH"] = _BIN + os.pathsep + os.environ.get("PATH", "")

# ---------- Paleta (somente tema escuro) ----------
ACCENT = "#F25F4C"
ACCENT_HOVER = "#D94A38"
BG = "#121318"
CARD = "#1B1D24"
CAMPO = "#23262F"
BORDA = "#2C2F3A"
TEXTO = "#E8EAED"
MUTED = "#9CA3AF"
VERDE = "#3DD68C"

PASTA_PADRAO = str(Path.home() / "Music" / "Baixador MP3")
QUALIDADES = {"Máxima": "0", "192 kbps": "192", "128 kbps": "128"}

ID_VIDEO = re.compile(r"[A-Za-z0-9_-]{11}")
RE_PROGRESSO = re.compile(r"^\[download\]\s+\d+(\.\d+)?%")


# ---------- Tratamento dos links ----------
def normalizar_link(texto, playlist):
    """Retorna (url, tipo). tipo: video | playlist | so_playlist | invalido | vazio."""
    texto = texto.strip()
    if not texto or texto.startswith("#"):
        return None, "vazio"
    if not texto.startswith(("http://", "https://")):
        texto = "https://" + texto
    try:
        p = urlparse(texto)
    except ValueError:
        return None, "invalido"

    host = p.netloc.lower()
    partes = [x for x in p.path.split("/") if x]
    qs = parse_qs(p.query)
    vid = ""
    if host.endswith("youtu.be"):
        vid = partes[0] if partes else ""
    elif "youtube.com" in host:
        if len(partes) >= 2 and partes[0] in ("shorts", "live", "embed"):
            vid = partes[1]
        else:
            vid = qs.get("v", [""])[0]
    else:
        return None, "invalido"

    vid = vid if ID_VIDEO.fullmatch(vid or "") else ""
    lista = qs.get("list", [""])[0]

    if playlist and lista:
        if vid:
            return f"https://www.youtube.com/watch?v={vid}&list={lista}", "playlist"
        return f"https://www.youtube.com/playlist?list={lista}", "playlist"
    if vid:
        return f"https://www.youtube.com/watch?v={vid}", "video"     # sem &list
    if lista:
        return None, "so_playlist"   # link só de playlist com a opção desligada
    return None, "invalido"


def analisar(texto, playlist):
    """Limpa, classifica e remove duplicados (a mesma playlist conta uma vez só)."""
    r = {"urls": [], "videos": 0, "playlists": 0, "duplicados": 0, "invalidos": 0, "so_playlist": 0}
    vistos = set()
    for item in texto.split():
        url, tipo = normalizar_link(item, playlist)
        if tipo == "vazio":
            continue
        if url is None:
            r["so_playlist" if tipo == "so_playlist" else "invalidos"] += 1
            continue
        chave = parse_qs(urlparse(url).query).get("list", [url])[0] if tipo == "playlist" else url
        if chave in vistos:
            r["duplicados"] += 1
            continue
        vistos.add(chave)
        r["urls"].append((url, tipo))
        r["videos" if tipo == "video" else "playlists"] += 1
    return r


def nome_pasta_seguro(nome):
    """Remove caracteres que o Windows não aceita em nomes de pasta."""
    nome = re.sub(r'[<>:"/\\|?*]', "", nome).strip(" .")
    return nome or datetime.now().strftime("%Y-%m-%d_%H%M")


def ler_txt(caminho):
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return Path(caminho).read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return ""


def fmt_mb(b):
    return f"{(b or 0) / 1048576:.1f} MB".replace(".", ",")


def fmt_tempo(seg):
    if seg is None:
        return ""
    m, s = divmod(int(seg), 60)
    return f"faltam {m}min {s:02d}s" if m else f"faltam {s}s"


def encurtar(texto, limite=62):
    return texto if len(texto) <= limite else texto[:limite - 1] + "…"


class LogFila:
    """Logger do yt-dlp que manda as mensagens para a interface."""
    def __init__(self, fila):
        self.fila = fila

    def debug(self, msg):
        if msg.startswith("[debug]") or RE_PROGRESSO.match(msg):
            return
        self.fila.put(("log", msg))

    info = debug

    def warning(self, msg):
        self.fila.put(("log", f"Aviso: {msg}"))

    def error(self, msg):
        self.fila.put(("log", f"Erro: {msg}"))


# ---------- Interface ----------
class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("Baixador de MP3")
        self._enquadrar()
        try:
            self.iconbitmap(recurso("icone.ico"))
        except Exception:
            pass

        self.fila = queue.Queue()
        self.cancelar = threading.Event()
        self.pasta_final = None
        self._baixadas = 0
        self._i_link = 0
        self._n_links = 1
        self._log_visivel = False

        self.f_titulo = ctk.CTkFont(size=22, weight="bold")
        self.f_secao = ctk.CTkFont(size=14, weight="bold")
        self.f_normal = ctk.CTkFont(size=13)
        self.f_pequena = ctk.CTkFont(size=12)
        self.f_musica = ctk.CTkFont(size=15, weight="bold")
        self.f_pct = ctk.CTkFont(size=20, weight="bold")

        # Corpo com rolagem: nada fica cortado em telas menores
        # Rodapé fixo (ações + progresso) sempre visível; o restante rola se faltar espaço
        self.rodape = ctk.CTkFrame(self, fg_color=BG)
        self.rodape.pack(side="bottom", fill="x")
        self.rodape.grid_columnconfigure(0, weight=1)
        self.corpo = ctk.CTkScrollableFrame(self, fg_color=BG, scrollbar_button_color=BORDA,
                                            scrollbar_button_hover_color=MUTED)
        self.corpo.pack(fill="both", expand=True)
        self.corpo.grid_columnconfigure(0, weight=1)

        self._cabecalho()
        self._card_links()
        self._card_config()
        self._barra_acoes()
        self._card_progresso()

        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.after(100, self._processar_fila)
        self._atualizar_contagem()

    def _enquadrar(self):
        """Ajusta o tamanho da janela à tela e centraliza."""
        try:
            escala = ctk.ScalingTracker.get_window_scaling(self)
        except Exception:
            escala = 1.0
        tela_l = int(self.winfo_screenwidth() / escala)
        tela_a = int(self.winfo_screenheight() / escala)
        largura = min(860, tela_l - 40)
        altura = min(860, tela_a - 90)       # sobra espaço para a barra de tarefas
        x = max(0, (tela_l - largura) // 2)
        y = max(0, (tela_a - altura) // 2 - 20)
        self.geometry(f"{largura}x{altura}+{x}+{y}")
        self.minsize(640, 520)

    # ----- blocos visuais -----
    def _card(self, linha, titulo=None, pai=None):
        card = ctk.CTkFrame(pai or self.corpo, fg_color=CARD, corner_radius=14, border_width=1,
                            border_color=BORDA)
        card.grid(row=linha, column=0, sticky="ew", padx=(16, 8) if pai is None else 16, pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)
        if titulo:
            ctk.CTkLabel(card, text=titulo, font=self.f_secao, text_color=TEXTO).grid(
                row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(10, 4))
        return card

    def _entrada(self, pai, **kw):
        return ctk.CTkEntry(pai, height=32, fg_color=CAMPO, border_color=BORDA, text_color=TEXTO, **kw)

    def _botao_sec(self, pai, texto, comando, altura=32, largura=100):
        return ctk.CTkButton(pai, text=texto, command=comando, height=altura, width=largura,
                             corner_radius=10, fg_color=CAMPO, border_width=1, border_color=BORDA,
                             text_color=TEXTO, hover_color=BORDA, text_color_disabled=MUTED)

    def _cabecalho(self):
        topo = ctk.CTkFrame(self.corpo, fg_color="transparent")
        topo.grid(row=0, column=0, sticky="ew", padx=(16, 8), pady=(14, 10))
        ctk.CTkLabel(topo, text="Baixador de MP3", font=self.f_titulo, text_color=TEXTO).pack(anchor="w")
        ctk.CTkLabel(topo, text="Cole os links do YouTube, escolha a pasta e clique em Baixar.",
                     font=self.f_normal, text_color=MUTED).pack(anchor="w")

    def _card_links(self):
        c = self._card(1, "1. Links")
        self.txt_links = ctk.CTkTextbox(c, height=110, font=self.f_pequena, wrap="none",
                                        fg_color=CAMPO, border_width=1, border_color=BORDA, text_color=TEXTO)
        self.txt_links.grid(row=1, column=0, columnspan=4, sticky="ew", padx=16)
        self.txt_links.bind("<KeyRelease>", self._atualizar_contagem)

        linha = ctk.CTkFrame(c, fg_color="transparent")
        linha.grid(row=2, column=0, columnspan=4, sticky="ew", padx=16, pady=(8, 12))
        linha.grid_columnconfigure(3, weight=1)
        self.btn_txt = self._botao_sec(linha, "Abrir .txt", self.abrir_txt)
        self.btn_txt.grid(row=0, column=0, padx=(0, 6))
        self.btn_colar = self._botao_sec(linha, "Colar", self.colar)
        self.btn_colar.grid(row=0, column=1, padx=(0, 6))
        self.btn_limpar = self._botao_sec(linha, "Limpar", self.limpar)
        self.btn_limpar.grid(row=0, column=2)
        self.lbl_contagem = ctk.CTkLabel(linha, text="", font=self.f_pequena, text_color=MUTED)
        self.lbl_contagem.grid(row=0, column=3, sticky="e")

    def _card_config(self):
        c = self._card(2, "2. Destino e opções")
        c.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(c, text="Pasta", font=self.f_normal, text_color=TEXTO).grid(
            row=1, column=0, sticky="w", padx=(16, 10))
        self.ent_base = self._entrada(c)
        self.ent_base.insert(0, PASTA_PADRAO)
        self.ent_base.grid(row=1, column=1, sticky="ew")
        self.btn_base = self._botao_sec(c, "Escolher", self.escolher_base)
        self.btn_base.grid(row=1, column=2, padx=(8, 16))

        ctk.CTkLabel(c, text="Subpasta", font=self.f_normal, text_color=TEXTO).grid(
            row=2, column=0, sticky="w", padx=(16, 10), pady=(8, 0))
        self.ent_nome = self._entrada(c, placeholder_text="Usa o nome do .txt ou a data de hoje")
        self.ent_nome.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 16), pady=(8, 0))

        ctk.CTkFrame(c, height=1, fg_color=BORDA).grid(row=3, column=0, columnspan=3, sticky="ew",
                                                         padx=16, pady=12)

        # Opções em duas colunas
        op = ctk.CTkFrame(c, fg_color="transparent")
        op.grid(row=4, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 12))
        op.grid_columnconfigure((0, 1), weight=1)

        self.sw_playlist = ctk.CTkSwitch(op, text="Baixar a playlist inteira", font=self.f_normal,
                                         text_color=TEXTO, progress_color=ACCENT, command=self._on_playlist)
        self.sw_playlist.grid(row=0, column=0, sticky="w")
        lim = ctk.CTkFrame(op, fg_color="transparent")
        lim.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(lim, text="Limite por playlist", font=self.f_normal, text_color=TEXTO).pack(
            side="left", padx=(0, 8))
        self.ent_limite = self._entrada(lim, width=100, placeholder_text="sem limite")
        self.ent_limite.pack(side="left")

        self.lbl_dica = ctk.CTkLabel(op, text="", font=self.f_pequena, text_color=MUTED,
                                     justify="left", anchor="w")
        self.lbl_dica.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))

        self.sw_capa = ctk.CTkSwitch(op, text="Capa e informações da música", font=self.f_normal,
                                     text_color=TEXTO, progress_color=ACCENT)
        self.sw_capa.select()
        self.sw_capa.grid(row=2, column=0, sticky="w")
        q = ctk.CTkFrame(op, fg_color="transparent")
        q.grid(row=2, column=1, sticky="w")
        ctk.CTkLabel(q, text="Qualidade", font=self.f_normal, text_color=TEXTO).pack(side="left", padx=(0, 8))
        self.seg_qualidade = ctk.CTkSegmentedButton(q, values=list(QUALIDADES), fg_color=CAMPO,
                                                    unselected_color=CAMPO, unselected_hover_color=BORDA,
                                                    selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
                                                    text_color=TEXTO)
        self.seg_qualidade.set("Máxima")
        self.seg_qualidade.pack(side="left")
        self._on_playlist()

    def _barra_acoes(self):
        b = ctk.CTkFrame(self.rodape, fg_color="transparent")
        b.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 10))
        b.grid_columnconfigure(0, weight=1)
        self.btn_baixar = ctk.CTkButton(b, text="Baixar MP3", height=44, corner_radius=12,
                                        font=ctk.CTkFont(size=16, weight="bold"), text_color="#FFFFFF",
                                        text_color_disabled="#FFE3DE",
                                        fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.iniciar)
        self.btn_baixar.grid(row=0, column=0, sticky="ew")
        self.btn_cancelar = self._botao_sec(b, "Cancelar", self.cancelar_download, altura=44, largura=110)
        self.btn_cancelar.configure(state="disabled")
        self.btn_cancelar.grid(row=0, column=1, padx=(8, 0))
        self.btn_abrir = self._botao_sec(b, "Abrir pasta", self.abrir_pasta, altura=44, largura=110)
        self.btn_abrir.grid(row=0, column=2, padx=(8, 0))

    def _card_progresso(self):
        c = self._card(1, pai=self.rodape)
        c.grid_configure(pady=(0, 14))
        c.grid_columnconfigure(0, weight=1)
        c.grid_columnconfigure(1, weight=0)     # barras ocupam a largura toda

        # Música atual + porcentagem grande
        topo = ctk.CTkFrame(c, fg_color="transparent")
        topo.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        topo.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(topo, text="BAIXANDO AGORA", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.lbl_musica = ctk.CTkLabel(topo, text="Nenhum download em andamento", font=self.f_musica,
                                       text_color=TEXTO, anchor="w")
        self.lbl_musica.grid(row=1, column=0, sticky="ew")
        self.lbl_pct = ctk.CTkLabel(topo, text="0%", font=self.f_pct, text_color=ACCENT)
        self.lbl_pct.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))

        self.bar_arquivo = ctk.CTkProgressBar(c, height=14, corner_radius=7, fg_color=CAMPO,
                                              progress_color=ACCENT)
        self.bar_arquivo.set(0)
        self.bar_arquivo.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 4))

        det = ctk.CTkFrame(c, fg_color="transparent")
        det.grid(row=2, column=0, sticky="ew", padx=16)
        det.grid_columnconfigure(0, weight=1)
        self.lbl_detalhe = ctk.CTkLabel(det, text="", font=self.f_pequena, text_color=MUTED, anchor="w")
        self.lbl_detalhe.grid(row=0, column=0, sticky="w")
        self.lbl_posicao = ctk.CTkLabel(det, text="", font=self.f_pequena, text_color=MUTED, anchor="e")
        self.lbl_posicao.grid(row=0, column=1, sticky="e")

        # Progresso total
        tot = ctk.CTkFrame(c, fg_color="transparent")
        tot.grid(row=3, column=0, sticky="ew", padx=16, pady=(12, 0))
        tot.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(tot, text="PROGRESSO TOTAL", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.lbl_total = ctk.CTkLabel(tot, text="0%", font=self.f_pequena, text_color=TEXTO)
        self.lbl_total.grid(row=0, column=1, sticky="e")
        self.bar_geral = ctk.CTkProgressBar(c, height=8, corner_radius=4, fg_color=CAMPO,
                                            progress_color=VERDE)
        self.bar_geral.set(0)
        self.bar_geral.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 8))

        rod = ctk.CTkFrame(c, fg_color="transparent")
        rod.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 10))
        rod.grid_columnconfigure(0, weight=1)
        self.lbl_status = ctk.CTkLabel(rod, text="Pronto.", font=self.f_pequena, text_color=TEXTO, anchor="w")
        self.lbl_status.grid(row=0, column=0, sticky="w")
        self.btn_log = ctk.CTkButton(rod, text="Mostrar detalhes", width=130, height=26,
                                     fg_color="transparent", text_color=MUTED, hover_color=BORDA,
                                     command=self._alternar_log)
        self.btn_log.grid(row=0, column=1, sticky="e")

        self.txt_log = ctk.CTkTextbox(c, height=110, font=ctk.CTkFont(family="Consolas", size=11),
                                      fg_color=CAMPO, text_color=MUTED, state="disabled", wrap="none")

    # ----- ações dos controles -----
    def abrir_txt(self):
        caminho = filedialog.askopenfilename(filetypes=[("Arquivos de texto", "*.txt"), ("Todos", "*.*")])
        if not caminho:
            return
        self.txt_links.delete("1.0", "end")
        self.txt_links.insert("1.0", ler_txt(caminho))
        self.ent_nome.delete(0, "end")
        self.ent_nome.insert(0, Path(caminho).stem)      # subpasta com o nome do .txt
        self._atualizar_contagem()

    def colar(self):
        try:
            texto = self.clipboard_get()
        except Exception:
            return
        atual = self.txt_links.get("1.0", "end").strip()
        self.txt_links.insert("end", ("\n" if atual else "") + texto.strip() + "\n")
        self._atualizar_contagem()

    def limpar(self):
        self.txt_links.delete("1.0", "end")
        self.ent_nome.delete(0, "end")
        self._atualizar_contagem()

    def escolher_base(self):
        pasta = filedialog.askdirectory(initialdir=self.ent_base.get() or None)
        if pasta:
            self.ent_base.delete(0, "end")
            self.ent_base.insert(0, pasta)

    def abrir_pasta(self):
        alvo = self.pasta_final or Path(self.ent_base.get())
        if alvo.exists():
            os.startfile(alvo)

    def _on_playlist(self):
        ligado = self.sw_playlist.get() == 1
        self.ent_limite.configure(state="normal" if ligado else "disabled")
        self.lbl_dica.configure(text=(
            "Ligado: links com &list= baixam a lista toda. Mixes (listas RD...) podem ter centenas de músicas."
            if ligado else
            "Desligado: baixa só o vídeo de cada link, mesmo que ele tenha &list=."))
        self._atualizar_contagem()

    def _atualizar_contagem(self, *_):
        a = analisar(self.txt_links.get("1.0", "end"), self.sw_playlist.get() == 1)
        if not a["urls"] and not a["invalidos"] and not a["so_playlist"]:
            self.lbl_contagem.configure(text="Nenhum link ainda")
            return
        partes = []
        if a["videos"]:
            partes.append(f"{a['videos']} vídeo(s)")
        if a["playlists"]:
            partes.append(f"{a['playlists']} playlist(s)")
        if a["duplicados"]:
            partes.append(f"{a['duplicados']} repetido(s)")
        if a["so_playlist"]:
            partes.append(f"{a['so_playlist']} só de playlist (ligue a opção)")
        if a["invalidos"]:
            partes.append(f"{a['invalidos']} inválido(s)")
        self.lbl_contagem.configure(text="  ·  ".join(partes))

    def _alternar_log(self):
        self._log_visivel = not self._log_visivel
        if self._log_visivel:
            self.txt_log.grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 14))
            self.btn_log.configure(text="Ocultar detalhes")
        else:
            self.txt_log.grid_remove()
            self.btn_log.configure(text="Mostrar detalhes")

    def _travar(self, travado):
        estado = "disabled" if travado else "normal"
        for w in (self.btn_baixar, self.btn_txt, self.btn_colar, self.btn_limpar, self.btn_base,
                  self.sw_playlist, self.sw_capa, self.seg_qualidade, self.ent_base, self.ent_nome):
            w.configure(state=estado)
        self.txt_links.configure(state=estado)
        self.ent_limite.configure(state="disabled" if travado or self.sw_playlist.get() != 1 else "normal")
        self.btn_cancelar.configure(state="normal" if travado else "disabled")
        self.btn_baixar.configure(text="Baixando..." if travado else "Baixar MP3")

    # ----- download -----
    def iniciar(self):
        if shutil.which("ffmpeg") is None:
            messagebox.showerror("FFmpeg não encontrado",
                                 "O FFmpeg é necessário para converter em MP3 e não foi encontrado.")
            return

        playlist = self.sw_playlist.get() == 1
        a = analisar(self.txt_links.get("1.0", "end"), playlist)
        if not a["urls"]:
            dica = ("\n\nAlguns links são só de playlist. Ligue \"Baixar a playlist inteira\"."
                    if a["so_playlist"] else "")
            messagebox.showwarning("Sem links", "Nenhum link válido do YouTube foi encontrado." + dica)
            return

        limite = self.ent_limite.get().strip() if playlist else ""
        if limite and not limite.isdigit():
            messagebox.showwarning("Limite inválido", "O limite por playlist precisa ser um número.")
            return

        nome = nome_pasta_seguro(self.ent_nome.get())
        self.ent_nome.delete(0, "end")
        self.ent_nome.insert(0, nome)
        self.pasta_final = Path(self.ent_base.get().strip() or PASTA_PADRAO) / nome
        try:
            self.pasta_final.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Erro ao criar a pasta", str(e))
            return

        cfg = {"playlist": playlist, "limite": int(limite) if limite else None,
               "capa": self.sw_capa.get() == 1, "qualidade": QUALIDADES[self.seg_qualidade.get()]}

        self._limpar_log()
        self._log(f"Pasta: {self.pasta_final}")
        if shutil.which("deno") is None:
            self._log("Aviso: Deno não encontrado. Alguns vídeos do YouTube podem falhar.")
        self.cancelar.clear()
        self._baixadas = 0
        self.bar_arquivo.set(0)
        self.bar_geral.set(0)
        self.lbl_pct.configure(text="0%")
        self.lbl_total.configure(text="0%")
        self.lbl_musica.configure(text="Preparando...")
        self.lbl_detalhe.configure(text="")
        self.lbl_posicao.configure(text="")
        self._travar(True)
        threading.Thread(target=self._executar, args=(a["urls"], self.pasta_final, cfg), daemon=True).start()

    def cancelar_download(self):
        self.cancelar.set()
        self.lbl_status.configure(text="Cancelando... (termina a conversão em andamento)")

    def _hook_download(self, d):
        """Chamado pelo yt-dlp durante o download (roda na thread de download)."""
        if self.cancelar.is_set():
            raise DownloadCancelled("Cancelado pelo usuário")
        info = d.get("info_dict") or {}
        titulo = info.get("title") or "..."
        idx = info.get("playlist_index")
        total_itens = info.get("n_entries") or info.get("playlist_count")

        if d.get("status") == "downloading":
            tam = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            baixado = d.get("downloaded_bytes") or 0
            frac = min(baixado / tam, 1.0) if tam else 0.0
            partes = [f"{fmt_mb(baixado)} de {fmt_mb(tam)}" if tam else fmt_mb(baixado)]
            if d.get("speed"):
                partes.append(f"{fmt_mb(d['speed'])}/s")
            if d.get("eta") is not None:
                partes.append(fmt_tempo(d["eta"]))
            detalhe = "   ·   ".join(partes)
        elif d.get("status") == "finished":
            frac, detalhe = 1.0, "Convertendo para MP3..."
        else:
            return

        # Progresso total: links concluídos + fração do link atual (considera playlists)
        if idx and total_itens:
            parcial = ((idx - 1) + frac) / total_itens
            posicao = f"Link {self._i_link + 1} de {self._n_links}   ·   música {idx} de {total_itens}"
        else:
            parcial = frac
            posicao = f"Música {self._i_link + 1} de {self._n_links}"
        geral = (self._i_link + parcial) / self._n_links
        self.fila.put(("arquivo", titulo, frac, detalhe, posicao, geral))

    def _hook_pos(self, d):
        if d.get("postprocessor") == "ExtractAudio" and d.get("status") == "finished":
            self._baixadas += 1
            self.fila.put(("status", f"{self._baixadas} música(s) prontas"))

    def _executar(self, urls, destino, cfg):
        falhas, cancelado = [], False
        self._n_links = len(urls)
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(destino / "%(title)s.%(ext)s"),
            "noplaylist": not cfg["playlist"],      # controla o download da playlist inteira
            "ignoreerrors": True,                   # pula vídeos indisponíveis sem parar tudo
            "windowsfilenames": True,
            "noprogress": True,
            "logger": LogFila(self.fila),
            "progress_hooks": [self._hook_download],
            "postprocessor_hooks": [self._hook_pos],
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                                "preferredquality": cfg["qualidade"]}],
        }
        if cfg["limite"]:
            opts["playlistend"] = cfg["limite"]
        if cfg["capa"]:
            opts["writethumbnail"] = True
            opts["postprocessors"] += [{"key": "FFmpegMetadata", "add_metadata": True},
                                       {"key": "EmbedThumbnail"}]
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                for i, (url, _tipo) in enumerate(urls):
                    if self.cancelar.is_set():
                        cancelado = True
                        break
                    self._i_link = i
                    self.fila.put(("log", f"\n=== [{i + 1}/{len(urls)}] {url}"))
                    try:
                        codigo = ydl.download([url])
                    except DownloadCancelled:
                        cancelado = True
                        break
                    except Exception as e:
                        self.fila.put(("log", f"Erro: {e}"))
                        codigo = 1
                    if codigo != 0:
                        falhas.append(url)
        except Exception as e:
            self.fila.put(("log", f"Erro inesperado: {e}"))
        self.fila.put(("fim", self._baixadas, falhas, cancelado or self.cancelar.is_set(), len(urls)))

    # ----- atualização da tela -----
    def _processar_fila(self):
        try:
            while True:
                msg = self.fila.get_nowait()
                tipo = msg[0]
                if tipo == "log":
                    self._log(msg[1])
                elif tipo == "status":
                    self.lbl_status.configure(text=msg[1])
                elif tipo == "arquivo":
                    _, titulo, frac, detalhe, posicao, geral = msg
                    self.lbl_musica.configure(text=encurtar(titulo))
                    self.bar_arquivo.set(frac)
                    self.lbl_pct.configure(text=f"{int(frac * 100)}%")
                    self.lbl_detalhe.configure(text=detalhe)
                    self.lbl_posicao.configure(text=posicao)
                    self.bar_geral.set(geral)
                    self.lbl_total.configure(text=f"{int(geral * 100)}%")
                elif tipo == "fim":
                    self._finalizar(*msg[1:])
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)

    def _finalizar(self, baixadas, falhas, cancelado, total):
        self._travar(False)
        self._on_playlist()
        if not cancelado:
            self.bar_geral.set(1)
            self.lbl_total.configure(text="100%")
            self.lbl_musica.configure(text="Tudo pronto!")
            self.lbl_detalhe.configure(text=f"{total} link(s) processado(s)")
        else:
            self.lbl_musica.configure(text="Download cancelado")
        resumo = f"{'Cancelado' if cancelado else 'Concluído'}: {baixadas} música(s) baixada(s)"
        if falhas:
            resumo += f", {len(falhas)} link(s) com falha"
            arq = self.pasta_final / "falhas.txt"
            arq.write_text("\n".join(falhas), encoding="utf-8")
            self._log(f"Links com falha salvos em: {arq}")
        self.lbl_status.configure(text=resumo + ".")
        self._log("\n" + resumo + ".")
        if not cancelado:
            if messagebox.askyesno("Baixador de MP3", resumo + ".\n\nAbrir a pasta agora?"):
                self.abrir_pasta()

    def _log(self, texto):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", texto + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _limpar_log(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    def _fechar(self):
        self.cancelar.set()
        self.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")      # somente tema escuro
    ctk.set_default_color_theme("blue")
    App().mainloop()
