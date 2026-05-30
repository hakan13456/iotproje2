#!/usr/bin/env python3
"""
FIT IoT-LAB Deney Raporu — MQTT-SN vs CoAP
Generates a PDF report with tables, charts and analysis.
"""
from pathlib import Path
from datetime import date
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable, KeepTogether, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register DejaVu (full Unicode / Turkish support)
_FONT_DIR = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("DejaVu",         f"{_FONT_DIR}/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-Bold",    f"{_FONT_DIR}/DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-Italic",  f"{_FONT_DIR}/DejaVuSans-Oblique.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-BoldItalic", f"{_FONT_DIR}/DejaVuSans-BoldOblique.ttf"))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("DejaVu",
    normal="DejaVu", bold="DejaVu-Bold",
    italic="DejaVu-Italic", boldItalic="DejaVu-BoldItalic")

FONT      = "DejaVu"
FONT_BOLD = "DejaVu-Bold"

RESULTS = Path(__file__).parent.parent / "results"
OUT     = RESULTS / "deney_raporu_mqttsn_vs_coap.pdf"

# ── Experiment data (from pcap_deep.py analysis) ──────────────────────────
DATA = {
    "MQTTSN_tree":   {"proto":"MQTT-SN","topo":"Ağaç",   "pkts":562, "sent":11, "rcvd":11, "pdr":100.0, "rtt_avg":15.9, "rtt_med":15.6, "rtt_p95":19.6, "rtt_std":1.3,  "note":"QoS-1, PUBACK"},
    "MQTTSN_linear": {"proto":"MQTT-SN","topo":"Doğrusal","pkts":726, "sent":2,  "rcvd":2,  "pdr":100.0, "rtt_avg":1.8,  "rtt_med":1.8,  "rtt_p95":1.8,  "rtt_std":0.1,  "note":"QoS-0, PINGRESP RTT"},
    "MQTTSN_star":   {"proto":"MQTT-SN","topo":"Yıldız",  "pkts":680, "sent":13, "rcvd":5,  "pdr":38.5,  "rtt_avg":2.0,  "rtt_med":2.0,  "rtt_p95":2.1,  "rtt_std":0.1,  "note":"QoS-0, PINGRESP RTT"},
    "CoAP_tree":     {"proto":"CoAP",   "topo":"Ağaç",   "pkts":163, "sent":33, "rcvd":28, "pdr":84.8,  "rtt_avg":21.8, "rtt_med":20.5, "rtt_p95":31.1, "rtt_std":884.5,"note":"CON/ACK"},
    "CoAP_linear":   {"proto":"CoAP",   "topo":"Doğrusal","pkts":147, "sent":21, "rcvd":13, "pdr":61.9,  "rtt_avg":18.0, "rtt_med":17.7, "rtt_p95":19.7, "rtt_std":1.0,  "note":"CON/ACK"},
    "CoAP_star":     {"proto":"CoAP",   "topo":"Yıldız",  "pkts":79,  "sent":31, "rcvd":31, "pdr":100.0, "rtt_avg":17.7, "rtt_med":17.4, "rtt_p95":19.0, "rtt_std":1.4,  "note":"CON/ACK"},
}


def build_styles():
    styles = getSampleStyleSheet()
    # Patch all default styles to use DejaVu
    for s in styles.byName.values():
        s.fontName = FONT
    styles.add(ParagraphStyle("Title2",    fontName=FONT_BOLD, fontSize=18, spaceAfter=8,  alignment=TA_CENTER))
    styles.add(ParagraphStyle("SubTitle",  fontName=FONT,      fontSize=11, spaceAfter=4,  alignment=TA_CENTER, textColor=colors.HexColor("#555555")))
    styles.add(ParagraphStyle("H1",        fontName=FONT_BOLD, fontSize=13, spaceBefore=14, spaceAfter=6,  textColor=colors.HexColor("#0D47A1")))
    styles.add(ParagraphStyle("H2",        fontName=FONT_BOLD, fontSize=11, spaceBefore=10, spaceAfter=4,  textColor=colors.HexColor("#1565C0")))
    styles.add(ParagraphStyle("Body",      fontName=FONT,      fontSize=10, leading=15, spaceAfter=6,  alignment=TA_JUSTIFY))
    styles.add(ParagraphStyle("Caption",   fontName=FONT,      fontSize=8,  alignment=TA_CENTER, textColor=colors.HexColor("#444444"), spaceAfter=10))
    styles.add(ParagraphStyle("CodeSmall", fontName="Courier", fontSize=8,  leading=11, spaceAfter=6))
    return styles


def tbl_style(header_color="#1565C0"):
    return TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), colors.HexColor(header_color)),
        ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
        ("FONTNAME",    (0,0), (-1,0), FONT_BOLD),
        ("FONTSIZE",    (0,0), (-1,0), 9),
        ("FONTNAME",    (0,1), (-1,-1), FONT),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#EEF2FF")]),
        ("FONTSIZE",    (0,1), (-1,-1), 9),
        ("GRID",        (0,0), (-1,-1), 0.4, colors.HexColor("#AAAAAA")),
        ("TOPPADDING",  (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
    ])


def results_table(styles):
    headers = ["Protokol", "Topoloji", "Toplam\nPaket", "Gönderilen", "Alınan",
               "PDR (%)", "RTT Ort.\n(ms)", "RTT Med.\n(ms)", "RTT p95\n(ms)", "Not"]
    rows = [headers]
    for key, d in DATA.items():
        rows.append([
            d["proto"], d["topo"], str(d["pkts"]),
            str(d["sent"]), str(d["rcvd"]),
            f"{d['pdr']:.1f}", f"{d['rtt_avg']:.1f}",
            f"{d['rtt_med']:.1f}", f"{d['rtt_p95']:.1f}",
            d["note"]
        ])
    col_w = [1.8*cm, 2.1*cm, 1.5*cm, 1.7*cm, 1.5*cm,
             1.4*cm, 1.7*cm, 1.7*cm, 1.6*cm, 3.5*cm]
    t = Table(rows, colWidths=col_w, repeatRows=1)
    t.setStyle(tbl_style())
    return t


def comparison_table(styles):
    headers = ["Metrik", "MQTT-SN Ağaç", "CoAP Ağaç", "MQTT-SN Yıldız", "CoAP Yıldız",
               "MQTT-SN Doğrusal", "CoAP Doğrusal"]
    def g(k, m): return DATA[k][m]
    rows = [
        headers,
        ["PDR (%)",
         f"{g('MQTTSN_tree','pdr'):.1f}", f"{g('CoAP_tree','pdr'):.1f}",
         f"{g('MQTTSN_star','pdr'):.1f}", f"{g('CoAP_star','pdr'):.1f}",
         f"{g('MQTTSN_linear','pdr'):.1f}", f"{g('CoAP_linear','pdr'):.1f}"],
        ["RTT Ort. (ms)",
         f"{g('MQTTSN_tree','rtt_avg'):.1f}", f"{g('CoAP_tree','rtt_avg'):.1f}",
         f"{g('MQTTSN_star','rtt_avg'):.1f}", f"{g('CoAP_star','rtt_avg'):.1f}",
         f"{g('MQTTSN_linear','rtt_avg'):.1f}", f"{g('CoAP_linear','rtt_avg'):.1f}"],
        ["RTT p95 (ms)",
         f"{g('MQTTSN_tree','rtt_p95'):.1f}", f"{g('CoAP_tree','rtt_p95'):.1f}",
         f"{g('MQTTSN_star','rtt_p95'):.1f}", f"{g('CoAP_star','rtt_p95'):.1f}",
         f"{g('MQTTSN_linear','rtt_p95'):.1f}", f"{g('CoAP_linear','rtt_p95'):.1f}"],
        ["Toplam Paket",
         str(g('MQTTSN_tree','pkts')), str(g('CoAP_tree','pkts')),
         str(g('MQTTSN_star','pkts')), str(g('CoAP_star','pkts')),
         str(g('MQTTSN_linear','pkts')), str(g('CoAP_linear','pkts'))],
    ]
    col_w = [3.2*cm] + [2.5*cm]*6
    t = Table(rows, colWidths=col_w, repeatRows=1)
    t.setStyle(tbl_style())
    return t


def img(path, width=16*cm):
    if Path(path).exists():
        return Image(str(path), width=width, height=10*cm)
    return Paragraph(f"[Sekil: {Path(path).name}]", getSampleStyleSheet()["Normal"])


def build(styles):
    s = styles

    def h(text, style="H1"):
        return Paragraph(text, s[style])

    def p(text):
        return Paragraph(text, s["Body"])

    def sp(n=6):
        return Spacer(1, n)

    story = []

    # ── Cover ────────────────────────────────────────────────────────
    story += [
        sp(40),
        Paragraph("DENEY RAPORU", s["Title2"]),
        sp(8),
        Paragraph("MQTT-SN ve CoAP Protokollerinin<br/>FIT IoT-LAB Üzerinde Karşılaştırmalı Analizi", s["SubTitle"]),
        sp(4),
        HRFlowable(width="80%", thickness=1.5, color=colors.HexColor("#1565C0")),
        sp(12),
        Paragraph("Öğrenci: Hakan Dönmez &nbsp;&nbsp;|&nbsp;&nbsp; No: 20010011038", s["SubTitle"]),
        Paragraph(f"Tarih: {date.today().strftime('%d %B %Y')}", s["SubTitle"]),
        Paragraph("FIT IoT-LAB — Saclay Sitesi, A8-M3 Düğümleri", s["SubTitle"]),
        sp(4),
        Paragraph("RIOT OS &nbsp;|&nbsp; 6LoWPAN/802.15.4 &nbsp;|&nbsp; RPL Routing", s["SubTitle"]),
        PageBreak(),
    ]

    # ── 1. Giriş ─────────────────────────────────────────────────────
    story += [
        h("1. Giriş"),
        p("Bu deney raporu, kısıtlı IoT ortamlarında yaygın olarak kullanılan iki uygulama katmanı "
          "protokolünün — <b>MQTT-SN (Message Queuing Telemetry Transport for Sensor Networks)</b> ve "
          "<b>CoAP (Constrained Application Protocol)</b> — performansını FIT IoT-LAB testbed üzerinde "
          "karşılaştırmalı olarak değerlendirmektedir."),
        p("Deneyler üç farklı ağ topolojisinde (ağaç, yıldız, doğrusal) 15 adet A8-M3 düğümü ile "
          "gerçekleştirilmiştir. Temel performans metrikleri olarak <b>Paket İletim Oranı (PDR)</b>, "
          "<b>Gidiş-Dönüş Gecikmesi (RTT)</b> ve <b>paket yapısı</b> Wireshark/tshark ile 802.15.4 "
          "kablosuz arayüzünden yakalanan PCAP dosyaları üzerinden analiz edilmiştir."),
        sp(),
    ]

    # ── 2. Deneysel Kurulum ───────────────────────────────────────────
    story += [
        h("2. Deneysel Kurulum"),
        h("2.1 Donanım ve Platform", "H2"),
        p("FIT IoT-LAB (Saclay sitesi) üzerinde çalışan <b>15× IoT-LAB A8-M3</b> düğümü kullanılmıştır. "
          "Her A8-M3 düğümü; Linux işletim sistemi çalıştıran ARM Cortex-A8 işlemci ve "
          "IEEE 802.15.4 AT86RF231 radyo modülüne sahip ARM Cortex-M3 ko-işlemciden oluşmaktadır. "
          "M3 üzerinde <b>RIOT OS</b> çalışmakta olup 6LoWPAN/802.15.4 üzerinde RPL (RFC 6550) "
          "yönlendirme protokolü kullanılmaktadır."),
    ]

    setup_data = [
        ["Parametre", "Değer"],
        ["Platform", "FIT IoT-LAB Saclay"],
        ["Düğüm tipi", "IoT-LAB A8-M3"],
        ["İşletim sistemi", "RIOT OS"],
        ["Radyo katmanı", "IEEE 802.15.4 (AT86RF231)"],
        ["Ağ katmanı", "6LoWPAN"],
        ["Yönlendirme", "RPL (DODAG)"],
        ["RF kanalı", "Kanal 26 (2.480 GHz)"],
        ["MQTT-SN kütüphanesi", "emcute (RIOT)"],
        ["CoAP kütüphanesi", "gcoap (RIOT)"],
        ["MQTT-SN broker", "mosquitto RSMB (A8 Linux)"],
        ["Toplam düğüm sayısı", "15"],
        ["Sınır yönlendirici", "1× A8-103 (border router)"],
        ["Sensör düğümleri", "14× (a8-97..a8-112)"],
    ]
    t = Table(setup_data, colWidths=[7*cm, 9*cm])
    t.setStyle(tbl_style())
    story += [sp(4), t, sp(8)]

    story += [
        h("2.2 Topoloji Tasarımı", "H2"),
        p("Ağaç topolojisi RPL protokolü ile otomatik oluşturulmuştur. TX güç seviyeleri ayarlanarak "
          "3 kademeli hiyerarşik yapı zorlanmıştır:"),
        Paragraph(
            "<b>Kademe 0 (kök):</b> a8-103 — Border router + RSMB broker<br/>"
            "<b>Kademe 1:</b> a8-101, 102, 105, 108 — TX: 0 dBm<br/>"
            "<b>Kademe 2:</b> a8-97, 98, 100, 104, 106 — TX: −10 dBm<br/>"
            "<b>Kademe 3 (yaprak):</b> a8-107, 109, 110, 111, 112 — TX: −17 dBm",
            s["Body"]),
        p("Yıldız topolojisinde tüm sensör düğümleri doğrudan border router'a bağlıdır. "
          "Doğrusal (linear) topolojide düğümler sıralı zincir biçiminde konumlandırılmıştır."),
        sp(),
    ]

    # ── 3. Metodoloji ─────────────────────────────────────────────────
    story += [
        h("3. Metodoloji"),
        h("3.1 MQTT-SN Deneyi", "H2"),
        p("Sınır yönlendirici düğümün A8 Linux tarafında RSMB (Really Small Message Broker) "
          "başlatılmıştır. M3 sensör düğümleri RIOT emcute kütüphanesi ile broker'a bağlanmış, "
          "<b>metrics/rtt</b> konusuna zaman damgalı yayın mesajları göndermiştir. "
          "Ağaç topolojisinde QoS-1 (PUBACK onaylı) kullanılmış; yıldız ve doğrusal topolojilerde "
          "QoS-0 (onaysız) kullanılmış, RTT ölçümü PINGREQ/PINGRESP mekanizmasıyla yapılmıştır."),
        h("3.2 CoAP Deneyi", "H2"),
        p("Bir düğüm CoAP sunucusu olarak yapılandırılmış, diğer düğümler istemci olarak "
          "<b>/metrics/rtt</b> kaynağına Confirmable (CON) POST isteği göndermiştir. "
          "RTT, istek gönderme zamanı ile ACK alım zamanı arasındaki fark olarak hesaplanmıştır. "
          "PDR, gönderilen CON isteği sayısına karşı alınan ACK sayısı oranıdır."),
        h("3.3 Wireshark / Tshark Analizi", "H2"),
        p("A8 düğümlerinin Linux tarafından <b>wpan0</b> arayüzü üzerinden 802.15.4 trafiği "
          "tshark ile yakalanmıştır. Yakalama dosyaları (.pcap) Scapy kütüphanesi ile Python'da "
          "analiz edilmiş; CoAP mesaj kimliklerine (Message-ID) ve MQTT-SN mesaj tiplerine "
          "göre RTT hesaplanmıştır."),
        sp(),
    ]

    # ── 4. Bulgular ────────────────────────────────────────────────────
    story += [
        h("4. Bulgular"),
        h("4.1 Tüm Topoloji/Protokol Kombinasyonları", "H2"),
        results_table(s),
        sp(4),
        Paragraph("Tablo 1: Tüm deneyler için PDR ve RTT ölçüm sonuçları", s["Caption"]),
    ]

    story += [
        h("4.2 Protokol Karşılaştırması", "H2"),
        comparison_table(s),
        sp(4),
        Paragraph("Tablo 2: Protokol ve topoloji bazlı karşılaştırma özeti", s["Caption"]),
    ]

    # Figures
    deep_png = RESULTS / "deep_comparison.png"
    if deep_png.exists():
        story += [
            sp(8),
            img(deep_png, width=16*cm),
            Paragraph("Şekil 1: RTT, PDR ve paket sayısı karşılaştırması — tüm topolojiler", s["Caption"]),
        ]

    # ── 5. Analiz ──────────────────────────────────────────────────────
    story += [
        PageBreak(),
        h("5. Analiz ve Tartışma"),
        h("5.1 Ağaç Topolojisi", "H2"),
        p("Ağaç topolojisinde MQTT-SN, QoS-1 mekanizması sayesinde <b>%100 PDR</b> ve "
          "<b>15.9 ms ortalama RTT</b> elde etmiştir. CoAP ise Confirmable mesajlarda "
          "%84.8 PDR ve 21.8 ms RTT kaydetmiştir. MQTT-SN'in broker üzerinden merkezi "
          "yönlendirmesi çok atlamalı ağaç yapısında daha kararlı çalışmıştır. "
          "CoAP'ın kayıp oranı (%15.2), 3 kademeli RPL ağacındaki çok atlamalı kayıplardan "
          "kaynaklandığı değerlendirilmektedir."),
        h("5.2 Yıldız Topolojisi", "H2"),
        p("Yıldız topolojisinde <b>CoAP %100 PDR ve 17.7 ms RTT</b> ile mükemmel performans "
          "gösterirken, MQTT-SN PINGRESP PDR'si %38.5'e düşmüştür. Bu durum MQTT-SN broker "
          "bağlantısının tek atlama ortamında bile zaman zaman kesildiğine işaret etmektedir. "
          "Çok düğümlü aynı anda bağlanma girişimleri (pcap'te 8× CONNECT/CONNACK gözlendi) "
          "broker'ı aşırı yüklemiş olabilir. CoAP'ın sunucu-istemci mimarisi yıldız topolojisine "
          "doğal olarak daha uyumludur."),
        h("5.3 Doğrusal Topoloji", "H2"),
        p("Doğrusal topolojide CoAP %61.9 PDR ve 18.0 ms RTT elde etmiştir. MQTT-SN QoS-0 ile "
          "çalışmış, sadece PINGREQ/PINGRESP ölçülebilmiş (2 örnek, 1.8 ms). Doğrusal ağdaki "
          "çok atlama sayısının CoAP CON/ACK kayıplarını artırdığı görülmektedir. "
          "MQTT-SN broker'ın bütün trafiği toplaması (aggregation) bu topolojide avantaj sağlayabilir "
          "ancak QoS-0 kullanımı nedeniyle iletim güvencesi bulunmamaktadır."),
        h("5.4 Protokol Karakteristikleri", "H2"),
        p("<b>MQTT-SN:</b> Yayın/abone (pub/sub) modeli broker bağımlılığı getirir. "
          "QoS-1 güvenilir iletim sağlar ancak broker yük noktası oluşturabilir. "
          "Bant genişliği açısından verimlidir; küçük başlık boyutu (2-5 bayt) kısıtlı düğümler "
          "için idealdir. Ağaç topolojisinde üstün performans gözlemlenmiştir."),
        p("<b>CoAP:</b> İstek/yanıt modeli merkezi broker gerektirmez; uçtan uca iletişim sağlar. "
          "Confirmable mesajlar yerleşik ACK mekanizması sunarak ölçüm kolaylığı sağlar. "
          "Yıldız topolojisinde %100 PDR elde edilmiştir. Çok atlamalı senaryolarda kayıp "
          "oranı artmaktadır."),
        sp(),
    ]

    # ── 6. Wireshark Gözlemleri ────────────────────────────────────────
    story += [
        h("6. Wireshark / Tshark Paket Analizi"),
        p("802.15.4 wpan0 arayüzünden yakalanan pcap dosyalarının analizi aşağıdaki "
          "trafik profillerini ortaya çıkarmıştır:"),
    ]

    ws_data = [
        ["Dosya", "Toplam Paket", "Süre (s)", "Bant Genişliği\n(pkt/s)", "Gözlem"],
        ["mqttsn_tree.pcap",   "562", "144.5", "3.9",  "PUBLISH+PUBACK çiftleri, RPL DIO/DAO"],
        ["mqttsn_linear.pcap", "726", "799.1", "0.9",  "Çok CONNECT girişimi, QoS-0 PUBLISH"],
        ["mqttsn_star.pcap",   "680", "2325.7","0.3",  "8× yeniden bağlanma, PINGRESP kayıpları"],
        ["coap_tree.pcap",     "163", "535.2", "0.3",  "CON/ACK çiftleri, 5 yanıtsız CON"],
        ["coap_linear.pcap",   "147", "635.1", "0.2",  "CON/ACK, 8 kayıp ACK (multi-hop)"],
        ["coap_star.pcap",     "79",  "142.4", "0.6",  "Tüm CON'lar ACK aldı — %100 PDR"],
    ]
    t = Table(ws_data, colWidths=[3.8*cm, 2.2*cm, 1.8*cm, 2.2*cm, 6.5*cm])
    t.setStyle(tbl_style())
    story += [sp(4), t, sp(4),
              Paragraph("Tablo 3: PCAP dosya analizi özeti", s["Caption"])]

    story += [
        p("MQTT-SN star deneyinde pcap'te <b>0x16 (PINGREQ) mesajları 13 kez, "
          "0x17 (PINGRESP) ise yalnızca 5 kez</b> gözlemlenmiştir (%38.5 yanıt oranı). "
          "Bu, keepalive mekanizmasının güvenilir çalışmadığını göstermektedir. "
          "CoAP ağaç deneyinde 33 CON mesajının 28'i ACK almış (%84.8), "
          "5 pakette 2 saniyelik timeout tetiklenmiştir."),
        sp(),
    ]

    # ── 7. Sonuç ──────────────────────────────────────────────────────
    story += [
        PageBreak(),
        h("7. Sonuç"),
        p("Bu çalışmada MQTT-SN ve CoAP protokolleri FIT IoT-LAB testbedinde üç farklı topoloji "
          "altında deneysel olarak karşılaştırılmıştır. Elde edilen bulgular şu şekilde özetlenebilir:"),
        Paragraph(
            "• <b>Ağaç topolojisi:</b> MQTT-SN (QoS-1) üstün PDR (%100 vs %84.8) ve düşük RTT "
            "(15.9 ms vs 21.8 ms) ile öne çıkmaktadır.<br/>"
            "• <b>Yıldız topolojisi:</b> CoAP mükemmel PDR (%100) ve düşük RTT (17.7 ms) ile "
            "MQTT-SN'i geride bırakmaktadır.<br/>"
            "• <b>Doğrusal topoloji:</b> CoAP %61.9 PDR ile ölçülebilir sonuç verirken, "
            "MQTT-SN QoS-0 sınırlı veri üretmiştir.<br/>"
            "• <b>Genel:</b> Her iki protokol de kısıtlı IoT ortamlarında uygulanabilir olmakla "
            "birlikte, seçim; topoloji yapısına, QoS gereksinimlerine ve broker/sunucu "
            "altyapısına göre yapılmalıdır.",
            s["Body"]),
        p("MQTT-SN, broker tabanlı merkezi toplama gerektiren hiyerarşik ağaç yapılarında "
          "avantajlıdır. CoAP ise broker gerektirmeyen, düz yıldız veya küçük ölçekli ağlarda "
          "tercih edilmelidir. Çok atlamalı senaryolarda her iki protokolde de kayıp oranlarının "
          "arttığı gözlemlenmiş; RPL ağacının kararlılığının deneysel performansı doğrudan "
          "etkilediği görülmüştür."),
        sp(8),
    ]

    # ── 8. Kaynaklar ──────────────────────────────────────────────────
    story += [
        h("8. Kaynaklar"),
        Paragraph('[1] Palmese et al., "CoAP vs. MQTT-SN Comparison and Performance Evaluation '
                  'in Publish-Subscribe Environments," WF-IoT 2019.', s["Body"]),
        Paragraph('[2] Adjih et al., "FIT IoT-LAB: A Large Scale Open Experimental IoT Testbed," '
                  'IEEE WF-IoT 2015.', s["Body"]),
        Paragraph("[3] RIOT OS Documentation — emcute / gcoap modules, https://riot-os.org", s["Body"]),
        Paragraph("[4] RFC 7252 — The Constrained Application Protocol (CoAP), IETF 2014.", s["Body"]),
        Paragraph("[5] OASIS MQTT-SN v1.2 Specification, 2013.", s["Body"]),
        Paragraph("[6] RFC 6550 — RPL: IPv6 Routing Protocol for Low-Power and Lossy Networks, IETF 2012.", s["Body"]),
        sp(20),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#AAAAAA")),
        Paragraph(
            f"Bu rapor FIT IoT-LAB Saclay sitesinde gerçekleştirilen deneyler ve "
            f"elde edilen pcap verileri temel alınarak üretilmiştir. Tarih: {date.today().strftime('%d.%m.%Y')}",
            s["Caption"]),
    ]

    return story


def main():
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        topMargin=2.5*cm,  bottomMargin=2.5*cm,
        title="Deney Raporu — MQTT-SN vs CoAP",
        author="Hakan Dönmez",
        subject="IoT Protokol Karşılaştırması",
    )
    styles = build_styles()
    story  = build(styles)
    doc.build(story)
    print(f"Rapor oluşturuldu → {OUT}")
    return OUT


if __name__ == "__main__":
    main()
