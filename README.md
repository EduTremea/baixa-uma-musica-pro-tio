# Baixador de MP3

Aplicativo para Windows que baixa o áudio de vídeos do YouTube em MP3. Você cola os links (ou abre um `.txt` com um link por linha), escolhe a pasta e clica em **Baixar MP3**.

Nasceu do pedido mais clássico de quem trabalha com TI: "grava umas músicas num pendrive pra mim?".

## Download

Baixe o `BaixadorMP3.exe` na página de [Releases](https://github.com/EduTremea/baixa-uma-musica-pro-tio/releases/latest) e execute. Não precisa instalar Python, yt-dlp nem FFmpeg, porque tudo vai dentro do executável.

Como o executável não tem assinatura digital, o Windows pode mostrar o aviso "O Windows protegeu o computador". Clique em **Mais informações** e depois em **Executar assim mesmo**.

## Como usar

1. Cole os links na caixa ou clique em **Abrir .txt**.
2. Escolha a pasta de destino. A subpasta recebe o nome do `.txt` ou, se você colou os links, a data de hoje.
3. Ajuste as opções, se quiser:
   - **Baixar a playlist inteira**: desligada, o app baixa só o vídeo de cada link, mesmo que ele tenha `&list=`. Ligada, baixa a playlist toda.
   - **Limite por playlist**: útil para mixes do YouTube (listas que começam com `RD`), que podem ter centenas de músicas.
   - **Capa e informações da música**: grava a miniatura do vídeo e os metadados no MP3.
   - **Qualidade**: máxima, 192 kbps ou 128 kbps.
4. Clique em **Baixar MP3** e acompanhe a música atual, a porcentagem, a velocidade e o progresso total.

Links repetidos são ignorados. Se algum link falhar, o app salva a lista em `falhas.txt` dentro da pasta de destino para você tentar de novo.

## Gerar o executável

Requisito: Windows com [Python 3.10 ou superior](https://www.python.org/downloads/).

Dê duplo clique no `build.bat`. Ele:

1. cria um ambiente virtual em `.venv-build`;
2. instala `yt-dlp[default]`, `customtkinter`, `imageio-ffmpeg`, `mutagen` e `pyinstaller`;
3. copia o FFmpeg para `bin/`;
4. baixa o Deno para `bin/`, porque o yt-dlp precisa de um runtime JavaScript para o YouTube;
5. gera `dist/BaixadorMP3.exe`.

Quando o YouTube muda algo e os downloads começam a falhar, rode o `build.bat` de novo para gerar um executável com o yt-dlp atualizado.

## Rodar pelo código

```bash
pip install "yt-dlp[default]" customtkinter
python baixador_mp3.py
```

Nesse caso, o FFmpeg e o Deno precisam estar no PATH.

## Estrutura

| Arquivo | Conteúdo |
| --- | --- |
| `baixador_mp3.py` | Código do aplicativo |
| `build.bat` | Script que gera o executável |
| `icone.ico` | Ícone do aplicativo |

## Projetos usados

O executável inclui estes projetos, cada um com a sua licença:

- [yt-dlp](https://github.com/yt-dlp/yt-dlp), que faz os downloads
- [FFmpeg](https://ffmpeg.org/legal.html), que converte o áudio para MP3
- [Deno](https://github.com/denoland/deno), que resolve os desafios JavaScript do YouTube
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), usado na interface

## Uso responsável

Use o app só para baixar conteúdo seu, conteúdo com licença livre (como Creative Commons) ou material que o autor autorizou. Os [termos do YouTube](https://www.youtube.com/t/terms) restringem o download de conteúdo sem permissão, e a responsabilidade pelo uso é de quem baixa.
