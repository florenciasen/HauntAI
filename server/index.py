from flask import Flask, jsonify, request, send_file
import os
import datetime
import logging
from flask_cors import CORS
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor
import shutil
import time
import google.generativeai as genai
import traceback
import re
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm, inch
from reportlab.lib.colors import Color

ignore_patterns = [
            r'localStorage\.getItem\([^)]+\)',  # Ignore localStorage calls
            r'userData\.address', # Ignore dynamic address data in React or JavaScript
            r'userData\.username',  # Ignore dynamic username data in React or JavaScript
            r'userData\.password',  # Ignore dynamic password data
            r'sessionStorage\.getItem\([^)]+\)',  # Ignore sessionStorage calls
            r'process\.env\.[\w\d]+',  # Ignore environment variables
            r'props\.[\w\d]+',  # Ignore React props
            r'context\.[\w\d]+',  # Ignore React context
            r'[\w]+\.password',  # Ignore object properties like password
            r'(?<!\w)@[\w.-]+\.[a-zA-Z]{2,}(?!\w)',  # Ignore strings like @MME_IT that are not proper email formats
            r'path\.join\([^)]+\)',  # Ignore paths constructed via path.join
            r'__dirname',  # Ignore paths involving __dirname
            r'express\.static\([^)]+\)',  # Ignore static file paths
            r'\/assets\/.*',  # Ignore static file paths (styles, images)
            r'\/public\/.*',  # Ignore public files (e.g., HTML, JS)
            r'localhost',  # Ignore localhost URLs (only loopback IPs)
            r'127\.0\.0\.1',  # Ignore loopback IPs
            r'\$login',  # Ignore any variable related to login (e.g., $login)
            r'\"api_key\"',  # Ignore literal API keys in strings
            r'\"apiKey\"',  # Ignore literal "apiKey" values in strings
            r'::1',  # Ignore IPv6 loopback
            r'(?<!\w)@[\w_]+(?!\.[a-zA-Z]{2,})\b', # Ignore '@handle' like Twitter/Instagram, but not email addresses
            r'\$\_[\w\d]+',  # Ignore variables like $_POST, $_SESSION, $_GET, etc.
            r"\$file\s*=\s*['\"][^'\"]+['\"]",  # Ignore any assignment to $file with string values (file paths)
            r"fopen\(\$file,\s*['\"]r['\"]\)",  # Ignore file open with read permissions
            r"\$banned\s*=\s*array\([^\)]*\)",  # Ignore hardcoded banned usernames list (like 'admin', 'passwords')
            r'From:\s*["\'][\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,6}["\']',  # Ignore email addresses used in "From:" header
            r'\{[^}]*apiKey[^}]*\}', # Mengabaikan objek yang mengandung apiKey
            r'\{.*apiUrl.*\}',  # Ignore object structures containing 'apiUrl' key
            r'\{.*siteUrl.*\}',  # Ignore object structures containing 'siteUrl' key
            r'\"[a-zA-Z]+Mode\":\s*\"[a-zA-Z]+\"',  # Ignore modes like "development", "production"
            r'\"[a-zA-Z]+Lang\":\s*\"[a-zA-Z]+\"',  # Ignore language settings
            r'http:\/\/localhost:\d{4}\/.*',  # Ignore full localhost URLs with a port
            r'\"(dependencies|devDependencies)\":\s*\{[^}]*\}',
            r'(\*{3}.*\*{3})',  # Ignore patterns that look like "*** Some Service Title ***"
            r'\"node_modules\"\s*:\s*\{[^}]*\}',  # Ignore node_modules block
            r'\"dependencies\"\s*:\s*\{[^}]*\}',  # Ignore entire dependencies block
            r'\"version\"\s*:\s*\"[\d\.]+\"',  # Ignore version fields like "version": "7.24.7"
            r'\"resolved\"\s*:\s*\"https:\/\/registry.npmjs.org[^"]*\"',  # Ignore resolved field in npm package
            r'\/(react-scripts|eslintConfig|dependencies|scripts|browserslist|private).*',  # Ignore paths like react-scripts, eslintConfig, dependencies
            r'\/.*\/(react-scripts|eslintConfig|browserslist|private).*',  # Nested paths with similar config values
            r'\/.*\.(json|js|xml|yml).*',  # Ignore JSON/JS configuration files and similar
            r'\/.*\/(node_modules|public|dist|build).*',  # Ignore common dev folders like node_modules, public, dist, build
            r'\/package\.json',  # Ignore package.json or any similar config files
            r'\/.*\/package\.json.*',  # Nested paths that contain package.json or similar
            r'\"[a-zA-Z]+Color\":\s*\"#[0-9a-fA-F]{6}\"',  # Ignore hex color codes (e.g., "themeColor": "#000000")
            r'\"[a-zA-Z]+Color\":\s*\"rgb\(\d{1,3},\s*\d{1,3},\s*\d{1,3}\)\"',  # Ignore RGB color values (e.g., "backgroundColor": "rgb(255, 255, 255)")
            r'\"[a-zA-Z]+Color\":\s*\"rgba\(\d{1,3},\s*\d{1,3},\s*\d{1,3},\s*[\d.]+\)\"',  # Ignore RGBA color values (e.g., "borderColor": "rgba(255, 0, 0, 0.5)")
            r'\b(?:support|noreply|default|sender_email|example)@[a-zA-Z0-9.-]+\.(?:com|org|net)\b',
            r'\$\{[a-zA-Z0-9_]+(?:Address)?\}@\$\{[a-zA-Z0-9_]+\}'
            r'e\.preventDefault\(\);', # Ignore JavaScript event handler preventDefault()
            r'echo\s*\$[a-zA-Z0-9_]+\s*[\+\.\*\/\-\=\(\)\[\]\{\};]*',  # Ignore any echo statement with variable output
            r'echo\s*".*"',  # Ignore any echo statement with string output
            r'echo\s*\'.*\'',  # Ignore any echo statement with string output (single quotes)
            r'$[\w\d_]+', # Ignore any variables in PHP or similar languages, e.g., $email, $sender
            r'Copyright.*',  # Ignore copyright-related lines
            r'<?php[\s\S]*?\?>'  # Ignore entire PHP blocks
            r'\b(?:\d{1,3}.){3}\d{1,3}\b',
            r'\.\.\.+', #ip
            r'IP\s+\.\.\.+', #ip
            r'\[\d{1,3}\]',  # Ignore detection for arrays with a single numeric value like [2], [100], etc.
            r"['\"]input\[name=['\"][^'\"]+['\"][\]]", # Ignore input field selectors
            r'<\s*\w+.*?class=["\'][^"\']*user[^"\']*["\'].*?>.*?</\s*\w+>',  # Ignore HTML with user-related placeholders (generic)
            r'<\s*\w+.*?class=["\'][^"\']*time[^"\']*["\'].*?>.*?</\s*\w+>',  # Ignore HTML with time-related placeholders (generic)
            r'<\s*\w+.*?>.*?[^<]*\b(?:comment|date|time)\b[^<]*</\s*\w+>',  # Ignore HTML with generic placeholders (user, date, etc.)
            r"\w+\s*=\s*.*?replace\(['\"][^'\"]+['\"][^)]+\);",  # Ignore JavaScript replace with placeholder values
            r'\b(?:comment|date|year|time|editor|bootstrap|affix)\b',  # Ignore general placeholders like comment, date, time
            r'document\.(getElementById|querySelector(All)?)\([^\)]*\)',#DOM and jquery
            r'\b[A-Za-z0-9_-]+\s+-\s+Mail\s+Header\s+Injection\s+\(SMTP\)\b',  # Ignore email header injection patterns
            r'function\s+\w+\([^\)]*\)',  # Ignore function definitions with parameters
            r"\b(?:elementId)\b",  # Ignore usage of elementId that sets the value of HTML elements
            r'\$[a-zA-Z][a-zA-Z0-9]*\s*=\s*[^\'"]*',  # Ignore variables with user/password-like names assigned anywhere
            r'\$[a-zA-Z_][a-zA-Z0-9_]*\s*(?![=:])',
            r'var\s+[a-zA-Z][a-zA-Z0-9]*\s*=\s*[^\'"]*',  # Ignore variables (usernames, passwords) assigned with values
            r'function\s+[a-zA-Z][a-zA-Z0-9]*\s*\([^)]*\)\s*{[^}]*\b(?:username|password|proxy).*}',  # Ignore functions that involve username or password
            r'\$\("#[a-zA-Z0-9_-]+"(?:\s*\[name=[^\]]+\])?\)',  # Ignore jQuery selectors 
            r'ace\.edit\("[a-zA-Z0-9_-]+"\)',  # Ignore ace editor calls
            r'var\s+[a-zA-Z0-9_]+\s*=\s*ace\.edit\(["\'][^"\']*["\']\);',  # Ignore general ace editor initialization (with dynamic selectors or IDs)
            r'[\w\s]*\=\s*["\'][^"\']*editor[^"\']*["\']\.',  # Ignore assignments to variables related to editor input
            r'\bwww\.[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',  # Ignore all strings that resemble URLs with 'www'
            r"\bmyVar\s*=>\s*array\(['\"]name['\"]\s*=>\s*['\"]myVar['\"]\s*,\s*['\"]type['\"]\s*=>\s*['\"]string['\"]\)",  # Ignore hardcoded username in complex type definitions
            r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}[^\s]*\?[^\s]*\b',  # Ignore URLs with query strings
            r'\.toLowerCase\(\)\s*\.\s*includes\([^\)]*\)',  # Ignore any .toLowerCase().includes() usage
            r'\.toUpperCase\(\)\s*\.\s*includes\([^\)]*\)',  # Ignore any .toUpperCase().includes() usage
            r'\.toLowerCase\(\)',  # Ignore any .toLowerCase() usage by itself
            r'\.toUpperCase\(\)',  # Ignore any .toUpperCase() usage by itself
            r'\.includes\([^\)]*\)',  # Ignore any .includes() usage
            r'\$\(.*\)\..+',  # Ignore jQuery calls or DOM manipulations
            r'\+.*Math\.random\(\)',  # Ignore concatenation with Math.random()
            r'new\s*Date\(\)',  # Ignore Date constructor usage
            r'(?<![@:\w/])\b(?!\d{5,}-)[a-zA-Z0-9-]+\.(co\.id|com|net|org|io|tech|id|info|biz|gov|edu|ac|me|gg|app|xyz)\b(?!\.\w)',
            r'(?<!["\'])(?<![=:\.])\b(?:username|name|user|email|emails|password|proxyusername|proxypassword|login|welcome|dba|ip|ip address|class|mac|license|path|server|hostname)\b(?!\s*[:=])',
            r'(?<!["\'])(?<![=:\.])\b(?:USERNAME|NAME|USER|EMAIL|EMAILS|PASSWORD|PROXYUSERNAME|PROXYPASSWORD|LOGIN|WELCOME|DBA|IP|IP Address|CLASS|MAC|LICENSE|PATH|SERVER|HOSTNAME)\b(?!\s*[:=])',
            r'<[^>]*>.*?</[^>]*>',  # Ignore full HTML elements including their content (e.g., <div>content</div>, <span>...</span>)
            r'"\s*(path|fs)\s*"\s*:\s*"[^"]*"',  # Ignore "path": "...", "fs": "..."
            r'"[a-zA-Z0-9_\-]+":\s*"[^"]*-security"',  # Ignore versions with '-security' suffix
            r"trackingNumber\s*:\s*\{\s*type\s*:\s*String\s*,\s*default\s*:\s*'[^']*'\s*\}", #ignore tracking number
            r'^(By|This|It|They|He|She|You|We|I)\b.*\b(email|emails)\b.*[\.\?!]?$',
            r"['\"]\s*(COMMENT|DATETIME|DATE|TIME|fs|editor)\s*['\"]",
            r'\[\s*["\'][^"\']+["\']\s*\]',
            r'result\[\w+\]\.description',  # Menangkap result[i].description, result[j].description, dst
            r'server\.replace\([^)]+\)',    # Menangkap server.replace(...) pattern
            r'\bN\/A\b',
            r'\$_(SESSION|COOKIE|POST|GET|REQUEST)\[[^\]]+\]',
            r'"[a-zA-Z0-9_\-]+":\s*"\^?[0-9]+\.[0-9]+\.[0-9]+"',
            r"^['\"]\s*['\"]$",
            r'\b[a-zA-Z0-9._%+-]+@\$\{[^}]+\}',
            r"(Bearer\s*['\"]?\s*\+\s*\w+)",
            r'"author"\s*:\s*"[^"]+"',                  
            r"'author'\s*:\s*'[^']+'",  
            r'\bauthor\s*:\s*[^\n]+',   
            r'\b(LATITUDE_OUTLET|LONGITUDE_OUTLET)\b',  
            r'(?<!@)\b[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.(co.id|com|net|org|io|tech)\b',
            r'\bhttps?:\/\/(?![^@\s]*@)(www\.)?(bit\.ly|t\.co|tinyurl\.com|goo\.gl|rb\.gy|rebrand\.ly|is\.gd|shorte\.st|cutt\.ly|[a-zA-Z0-9\-]+\.(com|co\.id|net|org|io|tech|id|info|biz|gov|edu|ac|me|gg|app|xyz))(\/[^\s\'"]*)?',
            r'\bdomain\s*:\s*[\'"][^\'"]+[\'"]', 
            r'"message"\s*=>\s*".*?"', 
            r'\b(include|include_once|require|require_once)\b\s*(\(\s*)?[\'"][^\'"]+[\'"]\s*(\))?',
            r'users\.data\[\w+\]\.(email|password)',
            r'^import\s+.*\s+from\s+[\'"][^\'"]+[\'"]',
            r'\$\{[^\}]+\}\/\$\{[^\}]+\}',
            r'style\s*=\s*"border:\s*\d+px\s*#[A-Fa-f0-9]{6}\s*solid"',
            r'\b(status|error|err|message|msg|description)\b\s*[:=]\s*[\'"][^\'"]+[\'"]',
            r'"(status|error|err|message|msg|description)"\s*:\s*"[^"]+"'
            r'(const|let|var)\s+\w+\s*=\s*(function|\(.*\)\s*=>)',
            r'\b(req|request|res|response|socket|remoteAddress|headers|params|query|body)\b',
            r'res\.(status|send|json|end)\s*\(.*?\)',
            r'res\.status\(\d+\)\.(send|json|end)\s*\(.*?\)',
            r'res\.(setHeader|redirect)\s*\(.*?\)',
            r'return\s+res\.(status|send|json|end)\s*\(.*?\)',
            r'([./]*lib/[\w/\.-]+)',
            r'\.css',  # Ignore .css files
            r'\.svg',  # Ignore .svg files
            r'\.png',  # Ignore .png files
            r'\.jpg',  # Ignore .jpg files
            r'\.jpeg',  # Ignore .jpeg files
            r'\.gif',  # Ignore .gif files
            r'\.webp',  # Ignore .webp files
            r'\.mp4',  # Ignore .mp4 video files
            r'\.mp3',  # Ignore .mp3 audio files
            r'\.wav',  # Ignore .wav audio files
            r'\.woff',  # Ignore .woff font files
            r'\.woff2',  # Ignore .woff2 font files
            r'\.ttf',  # Ignore .ttf font files
            r'\.eot',  # Ignore .eot font files
            r'\.otf',  # Ignore .otf font files
            r'\.ico',  # Ignore .ico icon files
            r'\.html',  # Ignore .html files
            r'\bDESCRIPTION\b',  # Description literal
            r'\bCODE\b',  # Common placeholder in assignment templates
            r'document\.cookie\s*=\s*["\'][^"\']*(;\s*)?Max-Age=0[^"\']*["\']',
            r'\b[a-zA-Z0-9._%+-]+@(example.com|example.net|example.org|test.com|test.net|test.org|dummy.com|fake.com|placeholder.com|invalid.com)\b'
        ]

country_names = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda", "Argentina", "Armenia", "Australia",
    "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin",
    "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso",
    "Burundi", "Cabo Verde", "Cambodia", "Cameroon", "Canada", "Central African Republic", "Chad", "Chile", "China",
    "Colombia", "Comoros", "Congo", "Costa Rica", "Croatia", "Cuba", "Cyprus", "Czech Republic", "Denmark", "Djibouti",
    "Dominica", "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea", "Estonia",
    "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Greece",
    "Grenada", "Guatemala", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Honduras", "Hungary", "Iceland", "India",
    "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya",
    "Kiribati", "Korea", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya",
    "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta",
    "Marshall Islands", "Mauritania", "Mauritius", "Mexico", "Micronesia", "Moldova", "Monaco", "Mongolia",
    "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Nepal", "Netherlands", "New Zealand",
    "Nicaragua", "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan", "Palau",
    "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland", "Portugal", "Qatar",
    "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia", "Saint Vincent and the Grenadines", "Samoa",
    "San Marino", "Sao Tome and Principe", "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone",
    "Singapore", "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Korea", "South Sudan",
    "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania",
    "Thailand", "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Tuvalu",
    "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom", "United States of America", "Uruguay", "Uzbekistan",
    "Vanuatu", "Vatican City", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe"
]

country_codes = [
    "AF", "AL", "DZ", "AD", "AO", "AG", "AR", "AM", "AU", "AT", "AZ", "BS", "BH", "BD", "BB", "BY", "BE", "BZ", "BJ",
    "BT", "BO", "BA", "BW", "BR", "BN", "BG", "BF", "BI", "CV", "KH", "CM", "CA", "CF", "TD", "CL", "CN", "CO", "KM",
    "CG", "CR", "HR", "CU", "CY", "CZ", "DK", "DJ", "DM", "DO", "EC", "EG", "SV", "GQ", "ER", "EE", "SZ", "ET", "FJ",
    "FI", "FR", "GA", "GM", "GE", "DE", "GH", "GR", "GD", "GT", "GN", "GW", "GY", "HT", "HN", "HU", "IS", "IN", "ID",
    "IR", "IQ", "IE", "IL", "IT", "JM", "JP", "JO", "KZ", "KE", "KI", "KR", "KW", "KG", "LA", "LV", "LB", "LS", "LR",
    "LY", "LI", "LT", "LU", "MG", "MW", "MY", "MV", "ML", "MT", "MH", "MR", "MU", "MX", "FM", "MD", "MC", "MN", "ME",
    "MA", "MZ", "MM", "NA", "NR", "NP", "NL", "NZ", "NI", "NE", "NG", "KP", "MK", "NO", "OM", "PK", "PW", "PS", "PA",
    "PG", "PY", "PE", "PH", "PL", "PT", "QA", "RO", "RU", "RW", "KN", "LC", "VC", "WS", "SM", "ST", "SA", "SN", "RS",
    "SC", "SL", "SG", "SK", "SI", "SB", "SO", "ZA", "SS", "ES", "LK", "SD", "SR", "SE", "CH", "SY", "TW", "TJ", "TZ",
    "TH", "TL", "TG", "TO", "TT", "TN", "TR", "TM", "TV", "UG", "UA", "AE", "GB", "US", "UY", "UZ", "VU", "VA", "VE",
    "VN", "YE", "ZM", "ZW"
    ]

        # Gabungkan ke regex pattern:
country_pattern = r'\b(?:' + '|'.join(re.escape(name) for name in country_names + country_codes) + r')\b'
ignore_patterns.append(country_pattern)


class PDFReportGenerator:
    def generate_pdf_report(self, analysis_result, output_path):
        def draw_watermark(canvas_obj, doc):
            canvas_obj.saveState()
            canvas_obj.setFont("Helvetica-Bold", 100)
            canvas_obj.setFillColor(Color(0, 0, 0.33, alpha=0.08))  # Transparent navy
            width, height = doc.pagesize
            canvas_obj.drawCentredString(width / 2.0, height / 2.0, "HauntAI")
            canvas_obj.restoreState()

        try:
            logger.info(f"Generating PDF report for {analysis_result['filename']}")

            doc = SimpleDocTemplate(
                output_path,
                pagesize=letter,
                leftMargin=2.5 * cm,
                rightMargin=2.5 * cm,
                topMargin=2 * cm,
                bottomMargin=2 * cm,
                title=f"Security Report - {analysis_result['filename']}" 
            )


            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                'TitleStyle',
                parent=styles['Heading1'],
                fontSize=16,
                alignment=1,
                spaceAfter=12
            )
            subtitle_style = ParagraphStyle(
                'SubtitleStyle',
                parent=styles['Heading2'],
                fontSize=13,
                alignment=0,
                spaceAfter=10
            )
            body_style = ParagraphStyle(
                'BodyStyle',
                parent=styles['Normal'],
                fontSize=10,
                alignment=4,
                spaceAfter=6
            )
            wrap_style = ParagraphStyle(
                'WrapStyle',
                parent=styles['Normal'],
                fontSize=9,
                alignment=0,
                wordWrap='CJK',
                spaceAfter=4
            )
            left_style = ParagraphStyle(
                'LeftStyle',
                parent=styles['Normal'],
                fontSize=10,
                alignment=0,
                spaceAfter=6
            )

            elements = []

            # Title and timestamp
            elements.append(Paragraph(f"Security Analysis Report - {analysis_result['filename']}", title_style))
            elements.append(Spacer(1, 0.25 * cm))
            elements.append(Paragraph(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", left_style))
            elements.append(Spacer(1, 0.75 * cm))

            if analysis_result.get('status') == 'error':
                elements.append(Paragraph(f"Error during analysis: {analysis_result.get('error', 'Unknown error')}", body_style))
            elif not analysis_result.get('results'):
                elements.append(Paragraph("No sensitive information found in this file.", body_style))
            else:
                for result_item in analysis_result.get('results', []):
                    content = result_item.get('content', '')
                    if content:
                        if len(analysis_result.get('results', [])) > 1:
                            elements.append(Paragraph(f"Split {result_item.get('split', 1)}", subtitle_style))
                            elements.append(Spacer(1, 0.25 * cm))
                        
                        table_data = self._extract_table_data(content)
                        
                        if table_data:
                            table_data.insert(0, [
                                Paragraph('Type', wrap_style),
                                Paragraph('CWE ID', wrap_style),
                                Paragraph('Line Number', wrap_style),
                                Paragraph('Snippet', wrap_style),
                                Paragraph('Recommendation', wrap_style)
                            ])

                            wrapped_table_data = []
                            for row in table_data:
                                wrapped_row = [Paragraph(cell, wrap_style) if not isinstance(cell, Paragraph) else cell for cell in row]
                                wrapped_table_data.append(wrapped_row)

                            available_width = 8.5 * inch - (2.5 * cm + 2.5 * cm)
                            col_widths = [
                                available_width * 0.17,
                                available_width * 0.10,
                                available_width * 0.10,
                                available_width * 0.31,
                                available_width * 0.32,
                            ]

                            table = Table(wrapped_table_data, colWidths=col_widths, repeatRows=1)
                            table.setStyle(TableStyle([
                                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('FONTSIZE', (0, 0), (-1, 0), 10),
                                ('FONTSIZE', (0, 1), (-1, -1), 8),
                                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                                ('TOPPADDING', (0, 0), (-1, -1), 6),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                            ]))

                            elements.append(Spacer(1, 0.1 * cm))
                            elements.append(table)
                            elements.append(Spacer(1, 0.8 * cm))

                            explanations = self._extract_explanations(content)
                            if explanations:
                                elements.append(Paragraph("Reason for Vulnerability:", subtitle_style))
                                elements.append(Spacer(1, 0.2 * cm))
                                for explanation in explanations:
                                    bullet_text = f"<font size=9>•</font> <font size=9>{explanation}</font>"
                                    elements.append(Paragraph(bullet_text, body_style))
                                elements.append(Spacer(1, 0.5 * cm))
                        else:
                            elements.append(Paragraph("No structured sensitive information found in the analysis.", body_style))
                    else:
                        error_msg = f"Error in split {result_item.get('split', 1)}: No content available"
                        elements.append(Paragraph(error_msg, body_style))
                    elements.append(Spacer(1, 0.5 * cm))

            # Build PDF with watermark on every page
            doc.build(elements, onFirstPage=draw_watermark, onLaterPages=draw_watermark)
            logger.info(f"PDF report generated successfully: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error generating PDF report: {str(e)}")
            traceback.print_exc()
            return False

    def _extract_table_data(self, text):
        """
        Extract table data from the analysis result text
        
        :param text: Analysis result text
        :return: List of table rows (each row is a list of columns)
        """
        table_data = []
        
        # Find the table section in the text
        table_section_match = re.search(r'\|.*?\|.*?\|.*?\|.*?\|.*?\|[\s\S]*?(?=\n\s*\n|\Z)', text)
        if not table_section_match:
            return []
        
        table_section = table_section_match.group(0)
        
        # Split by lines and process each row
        lines = table_section.strip().split('\n')
        if len(lines) < 3:  # Need at least header, separator, and one data row
            return []
        
        # Skip header (index 0) and separator (index 1)
        for line in lines[2:]:
            if '|' not in line:
                continue
                
            # Split the line by | character and remove empty entries
            parts = [part.strip() for part in line.split('|')]
            # Remove empty strings at the beginning and end (from splitting at the outer |)
            parts = [part for part in parts if part]
            
            if parts and len(parts) >= 3:  # Ensure we have at least some meaningful data
                table_data.append(parts)
        
        return table_data

    def _extract_explanations(self, text):
        """
        Extract vulnerability explanations from the analysis result text
        
        :param text: Analysis result text
        :return: List of explanations
        """
        explanations = []
        
        # Find the "Reason for Vulnerability" section
        reason_section_match = re.search(r'Reason for Vulnerability:(.*?)(?=###|$)', text, re.DOTALL)
        if not reason_section_match:
            return []
        
        reason_section = reason_section_match.group(1).strip()
        
        # Try to extract explanations with format "1. **Type:** Explanation"
        explanation_matches = re.findall(r'\d+\.\s*\*\*(.*?):\*\*\s*(.*?)(?=\d+\.\s*\*\*|\Z)', reason_section, re.DOTALL) 
        
        # If we found matches with the expected format
        if explanation_matches:
            for match in explanation_matches:
                if len(match) >= 2:
                    vul_type = match[0].strip()
                    explanation = match[1].strip()
                    explanations.append(f"{vul_type}: {explanation}")
        else:
            # Fallback: try to extract by splitting on numbered markers
            numbered_items = re.findall(r'\d+\.\s*(.*?)(?=\d+\.\s*|\Z)', reason_section, re.DOTALL)
            for item in numbered_items:
                if item.strip():
                    explanations.append(item.strip())
        
        return explanations

app = Flask(__name__)
CORS(app)

BASE_UPLOAD_FOLDER = os.path.join(os.path.expanduser("~"), "Documents", "HauntAI_Uploads")
TEMP_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, "temp")
MAX_CONTENT_LENGTH = 1024 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024 * 10 

os.makedirs(BASE_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_UPLOAD_FOLDER, exist_ok=True)

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

upload_status = {
    "uploaded": False,
    "analyzed": False,
    "current_session": None,
    "files_processed": 0
}

executor = ThreadPoolExecutor(max_workers=4)

ALLOWED_EXTENSIONS = {'.py', '.js', '.env', '.json', '.php', '.yaml', '.ts', '.yml'}
ALLOWED_FILENAMES = {'.env'}  # khusus untuk file tanpa ekstensi
ALLOWED_FILENAME_PREFIXES = {'.env.'}  # untuk .env.local, .env.production, dst

def allowed_file(filename):
    filename = filename.lower()
    name, ext = os.path.splitext(filename)

    return (
        ext in ALLOWED_EXTENSIONS or
        filename in ALLOWED_FILENAMES or
        any(filename.startswith(prefix) for prefix in ALLOWED_FILENAME_PREFIXES)
    )

# Configure Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDUkFwxDyAUbEZzemd4HNitryyacbL0QBI") 
genai.configure(api_key=GEMINI_API_KEY)

def save_chunk(chunk_data, chunk_path):
    # Simplified logging without duration or timestamps
    with open(chunk_path, 'wb') as f:
        f.write(chunk_data)
    logger.info(f"[CHUNK] Saved chunk to {chunk_path}")

@app.route('/upload-chunk', methods=['POST'])
def upload_chunk():
    if 'file' not in request.files:
        logger.error("[ERROR] No file chunk in request")
        return jsonify({"error": "No file chunk in request"}), 400
    
    file_chunk = request.files['file']
    session_id = request.form.get('sessionId')
    start_position = int(request.form.get('start'))
    filename = request.form.get('filename')
    total_size = int(request.form.get('total_size'))
    is_small_file = request.form.get('is_small_file', 'false').lower() == 'true'
    
    secure_name = filename
    total_size_mb = total_size/1024/1024
    
    logger.info(f"[UPLOAD] File: {secure_name} | Position: {start_position}/{total_size} | Size: {total_size_mb:.2f}MB")
    
    # Setup paths
    temp_session_folder = os.path.join(TEMP_UPLOAD_FOLDER, session_id)
    os.makedirs(temp_session_folder, exist_ok=True)
    
    # For small files (<= 30MB), save directly without chunking
    if is_small_file or total_size <= 30 * 1024 * 1024:  # 30MB in bytes
        try:
            direct_file_path = os.path.join(temp_session_folder, secure_name)
            with open(direct_file_path, 'wb') as f:
                f.write(file_chunk.read())
            
            file_size_mb = os.path.getsize(direct_file_path)/1024/1024
            logger.info(f"[COMPLETE] {secure_name}: 100% (Single file save: {file_size_mb:.2f}MB)")
            
            return jsonify({
                "message": "File uploaded successfully",
                "status": {
                    "filename": filename,
                    "position": total_size,
                    "total_size": total_size,
                    "direct_save": True
                }
            }), 200
        except Exception as e:
            logger.error(f"[ERROR] Direct file save failed: {e}")
            return jsonify({"error": str(e)}), 500
    
    # For files > 30MB, continue with chunking approach
    temp_folder = os.path.join(temp_session_folder, secure_name)
    os.makedirs(temp_folder, exist_ok=True)
    
    chunk_path = os.path.join(temp_folder, f"chunk_{start_position}")
    try:
        chunk_data = file_chunk.read()
        chunk_size_mb = len(chunk_data)/1024/1024
        with open(chunk_path, 'wb') as f:
            f.write(chunk_data)
        
        logger.info(f"[CHUNK] Saved chunk: {chunk_size_mb:.2f}MB to {chunk_path}")
        
        progress = (start_position + len(chunk_data)) / total_size * 100
        logger.info(f"[PROGRESS] {secure_name}: {progress:.1f}%")
        
        return jsonify({
            "message": "Chunk uploaded successfully",
            "status": {
                "filename": filename,
                "position": start_position,
                "total_size": total_size,
                "direct_save": False
            }
        }), 200
    except Exception as e:
        logger.error(f"[ERROR] Chunk save failed: {e}")
        return jsonify({"error": str(e)}), 500

def merge_file_chunks(source_folder, destination_path):
    filename = os.path.basename(destination_path)
    logger.info(f"[MERGE] Starting for {filename}")
    
    chunk_files = sorted(
        os.listdir(source_folder), 
        key=lambda x: int(x.split('_')[1])
    )
    
    with open(destination_path, 'wb') as outfile:
        buffer_size = 8 * 1024 * 1024  # 8MB buffer
        for chunk_name in chunk_files:
            chunk_path = os.path.join(source_folder, chunk_name)
            with open(chunk_path, 'rb') as chunk:
                shutil.copyfileobj(chunk, outfile, buffer_size)
    
    size_mb = os.path.getsize(destination_path) / 1024 / 1024
    logger.info(f"[MERGE] Completed {filename}: {size_mb:.2f}MB")


@app.route('/finalize-upload', methods=['POST'])
def finalize_upload():
    try:
        data = request.json
        session_id = data['sessionId']
        
        logger.info(f"[FINALIZE] Processing session {session_id}")
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        final_folder = os.path.join(BASE_UPLOAD_FOLDER, timestamp)
        analysis_folder = os.path.join(final_folder, "analysis")
        filtered_folder = os.path.join(final_folder, "files")

        os.makedirs(final_folder, exist_ok=True)
        os.makedirs(analysis_folder, exist_ok=True)
        os.makedirs(filtered_folder, exist_ok=True)

        session_temp_folder = os.path.join(TEMP_UPLOAD_FOLDER, session_id)
        saved_files = []
        futures = []

        # Filter dan pindahkan hanya file dengan ekstensi yang diperbolehkan
        for fname in os.listdir(session_temp_folder):
            fpath = os.path.join(session_temp_folder, fname)
            if os.path.isfile(fpath):
                _, ext = os.path.splitext(fname)
                if allowed_file(fname):
                    shutil.move(fpath, os.path.join(filtered_folder, fname))
                    logger.info(f"[FILTER] Accepted: {fname}")
                else:
                    os.remove(fpath)
                    logger.info(f"[FILTER] Removed: {fname}")
            elif os.path.isdir(fpath) and fname != "files":  # skip if already our 'files' folder
                # Merge chunks dari direktori sementara jika valid
                futures.append(
                    executor.submit(merge_file_chunks, fpath, os.path.join(filtered_folder, fname))
                )
                logger.info(f"[FILTER] Scheduled merge: {fname}")

        # Tunggu semua proses merge selesai
        for future in futures:
            future.result()

        for fname in os.listdir(filtered_folder):
            src = os.path.join(filtered_folder, fname)
            if os.path.isfile(src):
                saved_files.append(src)

        # Bersihkan folder temp session
        shutil.rmtree(session_temp_folder)
        logger.info(f"[FINALIZE] Completed successfully. Files saved: {len(saved_files)}")

        # Update status
        upload_status["uploaded"] = True
        upload_status["analyzed"] = False
        upload_status["current_session"] = final_folder

        return jsonify({
            "message": "Files uploaded and filtered successfully",
            "saved_files": saved_files,
            "folder": final_folder,
            "filtered_folder": filtered_folder,
            "upload_status": upload_status
        }), 200

    except Exception as e:
        logger.error(f"[ERROR] Finalize failed: {e}")
        upload_status["uploaded"] = False
        return jsonify({
            "error": str(e),
            "upload_status": upload_status
        }), 500


def analyze_file_with_gemini(file_path, analysis_prompt):
    """Analyze a file's content using Google's Gemini API with support for large files"""
    try:
        # Normalize file path to handle Windows backslashes
        file_path = os.path.normpath(file_path)
        filename = os.path.basename(file_path)
        logger.info(f"[ANALYSIS] Starting analysis for {filename} at path: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            logger.error(f"[ANALYSIS_ERROR] File not found: {file_path}")
            return {
                "filename": filename,
                "status": "error",
                "error": "File not found"
            }
        
        # Skip binary files based on extension
        binary_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.pdf', '.zip', '.exe', '.doc', '.docx']
        if any(filename.lower().endswith(ext) for ext in binary_extensions):
            logger.info(f"[ANALYSIS] Skipping binary file: {filename}")
            return {
                "filename": filename,
                "status": "skipped",
                "reason": "Binary file not supported for analysis"
            }
        
        # Read file content as text with error handling for encoding issues
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                file_content = f.read()
            
            total_lines = file_content.count('\n') + 1
            logger.info(f"[ANALYSIS] Successfully read {filename}, size: {len(file_content)} chars, {total_lines} lines")
        
        except Exception as read_error:
            logger.error(f"[ANALYSIS_ERROR] Failed to read {filename}: {read_error}")
            return {
                "filename": filename,
                "status": "error",
                "error": f"File reading error: {str(read_error)}"
            }

        # Define the maximum number of lines per split
        MAX_LINES_PER_SPLIT = 10000

        file_lines = file_content.split('\n')
        total_lines = len(file_lines)
        all_results = []
        
        # Function to analyze a split of the file
        def analyze_split(split_content, split_number=0, total_splits=1):
            split_info = f"(Split {split_number+1} of {total_splits})" if total_splits > 1 else ""
            logger.info(f"[ANALYSIS] Sending {filename} {split_info} to Gemini API")

            # Prepare prompt with file content
            prompt = f"""
            Analyze this code file thoroughly:
            
            Filename: {filename} {split_info}
            
            CODE CONTENT:
            
            {split_content}

            {analysis_prompt}
                    ### **TASK : Detect all sensitive data that is hardcoded based on below ** 

                    **1. Authentication Tokens**  
                    Detect only hardcoded Bearer tokens or authorization strings.  
                    Examples:  
                    - `'Bearer abc123xyz'`  
                    - `'Authorization: Bearer abc123xyz...'`  
                    CWE: CWE-798 (Use of Hard-coded Credentials)  


                    **2. Username**  
                    Hardcoded usernames may allow unauthorized access.  
                    Examples:  
                    - `'admin'`, `'root'`, `'user123'`  
                    CWE Reference: CWE-200 (Exposure of Sensitive Information to an Unauthorized Actor)  


                    **3. Email**  
                    Hardcoded emails can expose user identity.  
                    Example:  
                    - `'user@example.com'`  
                    CWE Reference: CWE-200 (Exposure of Sensitive Information to an Unauthorized Actor)   


                    **4. Password**  
                    Plaintext passwords in code are a severe security risk.  
                    Examples:  
                    - `'mypassword123'`, `'admin123'`, `'secretpass'`  
                    CWE Reference: CWE-259 (Use of Hard-coded Password)  


                    **5. Phone Number**  
                    Examples:  
                    - `'+1-800-555-1234'`, `'+62 812-3456-7890'`  
                    CWE Reference: CWE-200 (Exposure of Sensitive Information to an Unauthorized Actor)    


                    **6. Address**  
                    Examples:  
                    - `'1234 Elm Street'`, `'Jl. Sudirman No. 99, Jakarta'`  
                    CWE Reference: CWE-200 (Exposure of Sensitive Information to an Unauthorized Actor)   


                    **7. Credit Card Numbers**  
                    Examples:  
                    - `'4111 1111 1111 1111'`, `'3782 822463 10005'`  
                    CWE Reference: CWE-200 (Exposure of Sensitive Information to an Unauthorized Actor) 


                    **8. PII (Personally Identifiable Information)**  
                    Examples:  
                    - SSN (Social Security Number)
                    - passport ID
                    - NIK (Nomor Induk Kependudukan)
                    - NPWP (Nomor Pokok Wajib Pajak)
                    - KTP
                    - SIM
                    CWE Reference: CWE-200 (Exposure of Sensitive Information to an Unauthorized Actor)   


                    **9. License Keys**  
                    Examples:  
                    - `'XYZ123-45678-ABCD-EFGH'`  
                    CWE Reference: CWE-798 (Use of Hard-coded Credentials) 
                    

                    **10. Cryptographic Keys**  
                    Examples:  
                    - `'-----BEGIN PRIVATE KEY-----'`  
                    - `'-----BEGIN PUBLIC KEY-----'`  
                    - `'-----BEGIN RSA PRIVATE KEY-----'`  
                    CWE Reference: CWE-321 (Use of Hard-coded Cryptographic Key)  


                    **11. IP Addresses**  
                    Examples:  
                    - `'192.168.1.1'`, `'203.0.113.5'`  
                    CWE Reference:  
                    - CWE-284 (Improper Access Control)  
                    - CWE-359 (Exposure of Private Information in Client-Side)  
                    - CWE-297 (Improper Validation of Certificate with Host Mismatch) — if IP mismatch affects TLS validation  


                    **12. API Keys**  
                    Examples:  
                    - `'AKIAIOSFODNN7EXAMPLE'` (AWS)  
                    - `'AIzaSyABCDEF...'` (Google)  
                    - `'SG.XYz123abc456...'` (SendGrid)  
                    - `'ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'` (Twilio)  
                    CWE Reference: CWE-798 (Use of Hard-coded Credentials) 


                    **13. File Paths**  
                    Examples:  
                    - `'/home/user/config.json'`  
                    - `'C:\\Users\\Admin\\data.txt'`  
                    CWE References:  
                    - CWE-377: Insecure Temporary File  
                    - CWE-426: Untrusted Search Path  
                    - CWE-22: Path Traversal (if attacker can manipulate path)
                    - CWE-312: Cleartext Storage of Sensitive Information (if path points to sensitive config) 


                    **14. Database URI**  
                    Examples:  
                    - `'mongodb://admin:pass123@localhost:27017/mydb'`  
                    - `'postgresql://user:pass@localhost:5432/db'`  
                    CWE Reference**: CWE-798 (Use of Hard-coded Credentials). 


                    **15. Database Username**  
                    Examples:  
                    - `'admin'`, `'db_user'` (as literal)  
                    CWE Reference**: CWE-798 (Use of Hard-coded Credentials)

                    **16. Database Password**  
                    Examples:  
                    - `'mypassword'`, `'adminpass'`  
                    CWE Reference**: CWE-259 (Use of Hard-coded Password) 

                    **17. Session Tokens & Cookies**  
                    Examples:  
                    - `'session_token="abc123xyz"'`  
                    - `'sessionid="xyz98765"'`  
                    CWE Reference: CWE-315 (Cleartext Storage of Sensitive Information in a Cookie) 

                    **18. Cloud Storage Keys & Secrets**  
                    Examples:  
                    - `'AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE'`  
                    - `'AZURE_STORAGE_KEY=xyz123abc456...'`  
                    CWE Reference: CWE-798 (Use of Hard-coded Credentials) 


                    **19. Backup & Config Files**  
                    Examples:  
                    - `'config.bak'`, `'db_backup.sql'`, `'.env'`, `'settings.yml'`  
                    CWE References:  
                    - **CWE-538**: File and Directory Information Exposure  
                    - **CWE-530**: Exposure of Backup File to Unauthorized Control Sphere  
                    - **CWE-200**: Exposure of Sensitive Information to an Unauthorized Actor 


                    **20. Source Code Repo Credentials**  
                    Examples:  
                    - `'ghp_abcdef123456789'` (GitHub)  
                    - `'glpat-xyz123abc'` (GitLab)  
                    CWE Reference: CWE-798 (Use of Hard-coded Credentials) 


                    **21. Encryption Keys**  
                    Examples:  
                    - `'AES_SECRET_KEY="xyz123abc"'`  
                    - `'RSA_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----"'`  
                    CWE Reference: CWE-321 (Use of Hard-coded Cryptographic Key)  


                    **22. JWT Secret**  
                    Examples:  
                    - `'JWT_SECRET = "supersecretvalue"'`  
                    CWE Reference: CWE-798 (Use of Hard-coded Credentials) 
                    
                    **23. GitHub Repository Links**  
                    - Sniff out any hard‑coded GitHub URLs like `https://github.com/{'owner'}/{'repo'}`  
                    - Give the GitHub API a friendly poke to ask, “Hey, public party or secret speakeasy?”  
                    - **Only call out the secret speakeasies** (private repos); public ones get to roam free  
                    - CWE‑200 (Exposure of Sensitive Information) – because spilling secret repo beans is a no‑no!

                    **23. Location Coordinates**
                    Examples: 
                    - 'latLng = [34.05, -118.25]'
                    CWE Reference: CWE-200 (Exposure of Sensitive Information to an Unauthorized Actor)

                    **24. Account Number**
                    Examples:
                    '123-45678-90'
                    CWE Reference: CWE-359 (Exposure of Private Information)

                    **25. Client ID (OAuth / API Client Identifiers)**
                    Hardcoded Client IDs (seperti Google OAuth Client ID, Microsoft Application ID, GitHub OAuth App Client ID, dsb.) berpotensi disalahgunakan untuk enumerasi, abuse, atau pengungkapan identitas aplikasi.
                    Examples:
                    - '1005568560502-abcxyz123.apps.googleusercontent.com' (Google OAuth Client ID)
                    - 'd3590ed6-52b3-4102-aeff-aad2292ab01c' (Microsoft Application ID)
                    - 'Iv1.abcdef1234567890' (GitHub OAuth App Client ID)
                    - 'CLIENT_ID=abc123xyz987' (Generic API Client ID pattern)
                    CWE Reference: CWE-798 (Use of Hard-coded Credentials)

                    **26. Authorized Redirect URIs**
                    Detect hardcoded redirect URIs or proxy endpoints (e.g., uri, proxy, redirect_uri, redirectUri, authorizedRedirect) that may expose the app to misuse like open redirects or SSRF.
                    Examples:
                    - uri: "https://some-domain.com/redirect"
                    - proxy: "https://internal-service.example.com"
                    CWE References:
                    - CWE-601: URL Redirection to Untrusted Site
                    - CWE-918: Server-Side Request Forgery (SSRF)
                    - CWE-200: Exposure of Sensitive Information to an Unauthorized Actor (for misconfigured redirect URIs)

                    **27. Hardcoded User Roles / Privileges**
                    Detect hardcoded user roles or privilege levels that may lead to unauthorized access or privilege escalation.
                    Examples:
                    - 'role': 'admin'
                    - 'userRole': 'superuser'
                    - 'accessLevel': 'editor'
                    - 'privilege': 'viewer'
                    CWE References:
                    - CWE-266 (Incorrect Privilege Assignment)
                    - CWE-284 (Improper Access Control)
                    -  CWE-285 (Improper Authorization)

                    ### **Output Format:**  
                    Please structure the response using the following format for easy review:

                    #### **Sensitive Information Found**  
                    | Type                      | CWE ID  | Line Number | Snippet                                      | Recommendation                                                               |  
                    |---------------------------|---------|-------------|----------------------------------------------|-------------------------------------------------------------------------------|  
                    | API Key                   | CWE-798 | 23          | `API_KEY = '12345abc'`                       | Use environment variables or a secure secret management system.              |  
                    | Password                  | CWE-259 | 45          | `password = 'mypassword'`                    | Store passwords securely, use a hashing algorithm (e.g., bcrypt).             |  
                    | Database Credentials      | CWE-798 | 61          | `DB_URI = 'mongodb://localhost:27017/mydb'`  | Store in environment variables for database credentials.                      |  
                    | Session Token             | CWE-315 | 78          | `session_token = 'xyz123'`                   | Store tokens in secure storage and implement token invalidation on logout.   |

                    #### **Reason for Vulnerability:**

                    1. **API Key**: CWE-798 - Hardcoded API keys expose the application to misuse. They should be stored in environment variables or a secure vault system to prevent unauthorized access.

                    2. **Password**: CWE-259 - Hardcoding passwords in the code is insecure, as it can easily be exposed. Passwords must be stored securely and hashed before being saved.

                    3. **Database Credentials**: CWE-798 - Hardcoded database credentials can lead to unauthorized database access. These should be externalized into environment variables for security.

                    4. **Session Token**: CWE-315 - Hardcoded session tokens are a form of embedded credentials and may lead to unauthorized access or session hijacking. They should never be hardcoded, and if stored (e.g., in cookies), must be protected using `HttpOnly`, `Secure`, and encryption.

                    ### **DO NOT assume. DO NOT guess. ONLY analyze the provided literal code content.**
                    ### **Do not include any other parts or unwanted instructions.**   
                    ### **Make sure the analysis is not dependent on previous results**
                    ### **Always RESET AI before sending a new analysis**
                    ### **if there are the same results in different lines, still write them in the results**
                    ### **Do not duplicate existing results from the same line**
                    ### **ONLY DETECT EXPLICIT HARDCODED LITERAL STRINGS THAT ARE FULLY VISIBLE IN THE CODE.
                    ### **Please ignore fields like ‘name’, ‘username’ contained in dependencies and similar non-sensitive configuration fields commonly used in applications**
                    ### **Only detect hardcoded literal values, not the the logic code snippet**
                    ### **Every single line in the file MUST be independently and thoroughly checked for ALL 26 types of hardcoded sensitive data**
                    ### **Do NOT skip any category, including email, password, database URI, license key, JWT secret, etc**
                    ### **DO NOT assume that some categories are less important — every category MUST be checked and reported if found**
                    ### **If any sensitive data is found, it MUST be reported, even if it is the same value or pattern as a previous line**
                    ### **This prompt must ensure perfect accuracy — zero false positives and zero missed sensitive data**
                    ### **Other types of issues may be detected in the future, but detection of sensitive data must remain strictly accurate**
                    ### **DO NOT include "N/A" or empty fields in the results. If no sensitive data is found, no result should be generated for that type.**
                    
                    """

            try:
                model = genai.GenerativeModel("gemini-2.0-flash")
                response = model.generate_content(prompt)
                if not hasattr(response, 'text') or not response.text:
                    raise ValueError("Empty response from Gemini API")
                raw_result = response.text
                logger.info(f"[ANALYSIS] Received {len(raw_result)} chars from Gemini")
                return raw_result
            except Exception as api_error:
                logger.error(f"[ANALYSIS_ERROR] Gemini API error for {filename} split {split_number+1}: {api_error}")
                raise api_error
        
        time.sleep(10)

        # Check if file needs to be split (more than MAX_LINES_PER_SPLIT lines)
        file_lines = file_content.split('\n')
        total_lines = len(file_lines)
        
        # Store all results from each split
        all_results = []
        
        if total_lines > MAX_LINES_PER_SPLIT:
            logger.info(f"[ANALYSIS] File {filename} has {total_lines} lines, splitting into splits")
            
            # Calculate number of splits needed
            num_splits = (total_lines + MAX_LINES_PER_SPLIT - 1) // MAX_LINES_PER_SPLIT
            
            offset_lines = 0
            
            # Process each split
            for i in range(num_splits):
                start_idx = i * MAX_LINES_PER_SPLIT
                end_idx = min((i + 1) * MAX_LINES_PER_SPLIT, total_lines)
                split_content = '\n'.join(file_lines[start_idx:end_idx])
                split_size_kb = len(split_content) / 1024  # Split size in KB

                logger.info(f"[ANALYSIS] Processing split {i+1}/{num_splits} of {filename} (lines {start_idx+1}-{end_idx}, size: {split_size_kb:.2f}KB)")

                # Send each split for analysis
                try:
                    raw_result = analyze_split(split_content, i, num_splits)

                    # Apply filtering logic to each split
                    filtered_result, matched_log, removed_types = filter_analysis_result(raw_result, ignore_patterns)

                    # Clean up the analysis results for removed types
                    if removed_types:
                        for vuln_type in removed_types:
                            escaped = re.escape(vuln_type)
                            pattern = rf"\d+\.\s+\*\*{escaped}\*\*:.*?(?=\n\d+\.\s+\*\*|\Z)"
                            filtered_result = re.sub(pattern, "", filtered_result, flags=re.DOTALL).strip()

                    # Instead of saving to text file, add to results for PDF generation
                    all_results.append({
                        "split": i+1,
                        "content": filtered_result
                    })
                    
                    logger.info(f"[ANALYSIS] Processed split {i+1}/{num_splits} for {filename}")
                    
                except Exception as split_error:
                    logger.error(f"[ANALYSIS_ERROR] Failed to analyze split {i+1} of {filename}: {split_error}")
                    return {
                        "filename": filename,
                        "status": "error",
                        "error": f"Split {i+1} analysis failed: {str(split_error)}"
                    }

                # Update offset_lines for the next split
                offset_lines += (end_idx - start_idx)

                # Wait between API calls to avoid rate limiting
                if i < num_splits - 1:
                    time.sleep(10)
            
            # Check if any split contains actual sensitive data (not just headers) after filtering
            has_sensitive_data = False
            for result in all_results:
                # Extract table lines and count only data rows (not headers or separators)
                table_lines = [line for line in result["content"].split('\n') if '|' in line]
                data_rows = [line for line in table_lines if not line.startswith('| Type') and not line.startswith('|---')]
                if len(data_rows) > 0:
                    has_sensitive_data = True
                    break
                    
            if not has_sensitive_data:
                logger.info(f"[ANALYSIS] No sensitive data found in {filename} after filtering, skipping PDF generation")
                return {
                    "filename": filename,
                    "status": "skipped",
                    "reason": "No sensitive data found after filtering"
                }
            
            # Generate PDF report only if sensitive data was found
            pdf_generator = PDFReportGenerator()
            analysis_folder = os.path.join(upload_status["current_session"], "analysis")
            os.makedirs(analysis_folder, exist_ok=True)
            pdf_path = os.path.join(analysis_folder, f"report_{filename}.pdf")
            
            pdf_result = pdf_generator.generate_pdf_report({
                "filename": filename,
                "results": all_results
            }, pdf_path)
            
            if pdf_result:
                logger.info(f"[ANALYSIS] PDF report generated for {filename}")
            else:
                logger.error(f"[ANALYSIS] Failed to generate PDF report for {filename}")
            
            # Return the result with PDF path
            return {
                "filename": filename,
                "status": "success",
                "splits": num_splits,
                "total_lines": total_lines,
                "results": all_results,
                "pdf_path": pdf_path if pdf_result else None
            }
        else:
            # For files that don't need to be split
            try:
                raw_result = analyze_split(file_content)
                filtered_result, matched_log, removed_types = filter_analysis_result(raw_result, ignore_patterns)
                
                # Extract table lines and check for actual data rows after filtering
                table_lines = [line for line in filtered_result.split('\n') if '|' in line]
                data_rows = [line for line in table_lines if not line.startswith('| Type') and not line.startswith('|---')]
                
                if len(data_rows) > 0:
                    # Generate PDF report only if there's actual sensitive data
                    pdf_generator = PDFReportGenerator()
                    analysis_folder = os.path.join(upload_status["current_session"], "analysis")
                    os.makedirs(analysis_folder, exist_ok=True)
                    pdf_path = os.path.join(analysis_folder, f"report_{filename}.pdf")
                    
                    pdf_result = pdf_generator.generate_pdf_report({
                        "filename": filename,
                        "results": [{
                            "split": 1,
                            "content": filtered_result
                        }]
                    }, pdf_path)
                    
                    if pdf_result:
                        logger.info(f"[ANALYSIS] PDF report generated for {filename}")
                    else:
                        logger.error(f"[ANALYSIS] Failed to generate PDF report for {filename}")
                    
                    return {
                        "filename": filename,
                        "status": "success",
                        "splits": 1,
                        "total_lines": total_lines,
                        "results": [{
                            "split": 1,
                            "content": filtered_result
                        }],
                        "pdf_path": pdf_path if pdf_result else None
                    }
                else:
                    # Skip if no sensitive data after filtering
                    logger.info(f"[ANALYSIS] No sensitive data found in {filename}, skipping PDF generation")
                    return {
                        "filename": filename,
                        "status": "skipped",
                        "reason": "No sensitive data found after filtering"
                    }
            
            except Exception as e:
                logger.error(f"[ANALYSIS_ERROR] Failed to analyze {filename}: {e}")
                return {
                    "filename": filename,
                    "status": "error",
                    "error": str(e)
                }

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"[ANALYSIS_ERROR] {filename}: {e}\n{error_trace}")
        return {"filename": filename, "status": "error", "error": str(e)}


@app.route('/view-pdf', methods=['GET'])
def download_pdf():
    try:
        filename = request.args.get('filename')
        if not filename:
            return jsonify({"error": "No filename provided"}), 400
            
        session_folder = upload_status.get("current_session")
        analysis_folder = os.path.join(session_folder, "analysis")
        pdf_path = os.path.join(analysis_folder, f"report_{filename}.pdf")

        if not os.path.exists(pdf_path):
            return jsonify({"error": "PDF report not found"}), 404

        # View instead of force download
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=f"security_report_{filename}.pdf"
        )
        
    except Exception as e:
        logger.error(f"[DOWNLOAD_ERROR] Failed to load PDF report: {e}")
        return jsonify({"error": str(e)}), 500

    
def filter_analysis_result(raw_result, ignore_patterns):
    """Filter out sensitive information based on ignore patterns and log the ignored patterns."""
    # Loop through ignore patterns and remove matched lines from the result
    filtered_result = raw_result
    matched_log = []  # To store matched patterns
    removed_types = []  # To store the types of removed patterns
    seen_combinations = set()
    
    # Find table in analysis results
    table_pattern = r"\| Type\s+\| CWE ID\s+\| Line Number\s+\| Snippet\s+\| Recommendation\s+\|[\s\S]+?(?=\n\n|$)"
    table_match = re.search(table_pattern, filtered_result)
    
    if table_match:
        table_content = table_match.group(0)
        
        # Split table into rows
        table_rows = table_content.strip().split('\n')
        header_row = table_rows[0]
        separator_row = table_rows[1] if len(table_rows) > 1 else ""
        content_rows = table_rows[2:] if len(table_rows) > 2 else []
        
        # Filter rows based on ignore_patterns
        filtered_rows = []
        filtered_row_indices = []
        
        for i, row in enumerate(content_rows):
            should_keep = True
            columns = [col.strip() for col in row.split('|')]
            line_number = columns[3] if len(columns) > 3 else ""
            snippet = columns[4] if len(columns) > 4 else ""
            
            # Create a unique key for this line+snippet combination
            line_snippet_key = f"{line_number}:{snippet}"
            
            # Check if we've already seen this combination
            if line_snippet_key in seen_combinations:
                should_keep = False
                filtered_row_indices.append(i)
                continue
                
            for pattern in ignore_patterns:
                # ONLY check against line number and snippet (columns 2 and 3)
                combined_target = f"{line_number} {snippet}"
                matches = re.findall(pattern, combined_target)
                if matches:
                    matched_log.append((pattern, [row]))
                    logger.info(f"[FILTER] Pattern: {pattern}")
                    for example in matches[:3]:
                        logger.info(f"    → {example}")
                    if len(matches) > 3:
                        logger.info(f"    ...and {len(matches) - 3} more lines")
                    should_keep = False
                    type_match = re.search(r"\|\s*([^|]+?)\s*\|", row)
                    if type_match:
                        type_name = type_match.group(1).strip()
                        if type_name not in removed_types:
                            removed_types.append(type_name)
                    break
            
            if should_keep:
                seen_combinations.add(line_snippet_key)  # Add to seen combinations
                filtered_rows.append(row)
            else:
                filtered_row_indices.append(i)
        
        # Reconstruct table after filtering
        if filtered_rows:
            new_table = '\n'.join([header_row, separator_row] + filtered_rows)
            filtered_result = filtered_result.replace(table_content, new_table)
        else:
            # If all rows were filtered, remove the entire table section
            section_pattern = r"#### \*\*Sensitive Information Found\*\*\s*\n[\s\S]*?(?=\n\n####|\Z)"
            filtered_result = re.sub(section_pattern, "", filtered_result)
            # Add a clear message that no sensitive data was found
            filtered_result = filtered_result.replace(table_content, "No sensitive information found after filtering.")
        
        # Remove reasons for each filtered type
        for type_name in removed_types:
            # Find and remove reasons for filtered types
            reason_pattern = rf"\d+\.\s+\*\*{re.escape(type_name)}\*\*:.*?(?=\n\d+\.\s+\*\*|\Z)"
            filtered_result = re.sub(reason_pattern, "", filtered_result, flags=re.DOTALL)
        
        # Clean up result from excessive blank lines
        filtered_result = re.sub(r'\n{3,}', '\n\n', filtered_result)
    
    return filtered_result, matched_log, removed_types


@app.route('/analyze-files', methods=['POST'])
def analyze_files():
    try:
        data = request.json
        files = data.get('files', [])
        analysis_prompt = data.get('analysisPrompt', 'Analyze this code for security issues and best practices.')
        
        if not files:
            logger.error("[ANALYSIS] No files provided for analysis")
            return jsonify({"error": "No files provided for analysis"}), 400
            
        logger.info(f"[ANALYSIS] Starting analysis for {len(files)} files")
        
        # Ensure all file paths are valid
        valid_files = []
        for file_path in files:
            if os.path.exists(file_path):
                valid_files.append(file_path)
            else:
                logger.error(f"[ANALYSIS] File not found: {file_path}")
        
        if not valid_files:
            logger.error("[ANALYSIS] No valid files found for analysis")
            return jsonify({"error": "No valid files found for analysis"}), 400
            
        logger.info(f"[ANALYSIS] Found {len(valid_files)} valid files for analysis")

        total_valid_files = len(valid_files)
        
        # Determine session folder to store analysis results
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        session_folders = [d for d in os.listdir(BASE_UPLOAD_FOLDER) if os.path.isdir(os.path.join(BASE_UPLOAD_FOLDER, d)) and d.startswith(current_date)]
        if session_folders:
            latest_session = max(session_folders, key=lambda x: os.path.getctime(os.path.join(BASE_UPLOAD_FOLDER, x)))
        else:
            latest_session = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        session_folder = os.path.join(BASE_UPLOAD_FOLDER, latest_session)
        session_analysis_folder = os.path.join(session_folder, "analysis")
        os.makedirs(session_analysis_folder, exist_ok=True)
        
        # Process files one by one
        results = []
        for index, file_path in enumerate(valid_files, start=1):
            logger.info(f"[ANALYSIS] ({index}/{total_valid_files}) Processing: {os.path.basename(file_path)}")

            # Call function to analyze each file
            result = analyze_file_with_gemini(file_path, analysis_prompt)
            
            # Make sure we got a result
            if result is not None:
                results.append(result)
                logger.info(f"[ANALYSIS] Result for {result['filename']}: {result['status']}")
            else:
                logger.error(f"[ANALYSIS] No result returned for {file_path}")
                results.append({
                    "filename": os.path.basename(file_path),
                    "status": "error",
                    "error": "No analysis result returned"
                })
            
            # Delay between API calls to avoid rate limiting
            time.sleep(10)
            
        # Collect results
        successful_files = [r['filename'] for r in results if r['status'] == 'success']
        error_files = [r for r in results if r['status'] == 'error']
        skipped_files = [r for r in results if r['status'] == 'skipped']
        
        logger.info(f"[ANALYSIS] Analysis complete. Success: {len(successful_files)}, Errors: {len(error_files)}, Skipped: {len(skipped_files)}")
        
        # Log each error with details
        for error in error_files:
            logger.error(f"[ANALYSIS_ERROR] {error['filename']}: {error.get('error', 'Unknown error')}")
        
        # Update status
        upload_status["analyzed"] = True
        upload_status["files_processed"] = len(successful_files)
        
        return jsonify({
            "message": f"Analysis completed for {len(successful_files)} files",
            "analyzed_files": successful_files,
            "error_files": [e['filename'] for e in error_files],
            "skipped_files": [s['filename'] for s in skipped_files],
            "analysis_results": results,
            "upload_status": upload_status
        }), 200
        
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"[ANALYSIS_ERROR] Analysis request failed: {e}\n{error_trace}")
        return jsonify({
            "error": str(e),
            "stack_trace": error_trace,  # Include stack trace for debugging
            "upload_status": upload_status
        }), 500

@app.route('/download-analysis', methods=['GET'])
def download_analysis():
    try:
        filename = request.args.get('filename')
        pretty = request.args.get('pretty', 'false').lower() == 'true'
        if not filename:
            return jsonify({"error": "No filename provided"}), 400
            
        session_folder = upload_status.get("current_session")
        analysis_folder = os.path.join(session_folder, "analysis")
        analysis_path = os.path.join(analysis_folder, f"analysis_{filename}.txt")

        if not os.path.exists(analysis_path):
            return jsonify({"error": "Analysis file not found"}), 404
            
        with open(analysis_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return jsonify({
            "filename": filename,
            "content": content
        }), 200, {'Content-Type': 'application/json; charset=utf-8'}
        
    except Exception as e:
        logger.error(f"[DOWNLOAD_ERROR] Failed to download analysis: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify(upload_status)

# Add a simple test endpoint to verify the Gemini API is working
@app.route('/test-gemini', methods=['GET'])
def test_gemini():
    try:
        logger.info("[TEST] Testing Gemini API connection")
        # Pastikan model yang benar digunakan
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Mencoba mengirimkan konten uji
        response = model.generate_content("Hello, please respond with a short test message.")
        
        # Memastikan respon ada dan valid
        if not response or not hasattr(response, 'text'):
            raise ValueError("Empty or invalid response from Gemini API")
        
        # Log hasil respon untuk pengecekan
        logger.info(f"[TEST] Gemini API test successful: {response.text}")
        
        return jsonify({
            "status": "success",
            "message": "Gemini API is working",
            "response": response.text
        }), 200
        
    except Exception as e:
        logger.error(f"[TEST_ERROR] Gemini API test failed: {e}")
        return jsonify({
            "status": "error",
            "message": "Gemini API test failed",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    logger.info(f"[START] Server running. Upload folder: {BASE_UPLOAD_FOLDER}")
    # Test Gemini API on startup
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content("Test")
        logger.info(f"[START] Gemini API test successful: {response.text}")
    except Exception as e:
        logger.error(f"[START] Gemini API test failed: {e}. Please check your API key.")
    
    app.run(debug=True, host='0.0.0.0', port=5001)