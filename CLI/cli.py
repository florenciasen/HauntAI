import os
import datetime
import logging
import shutil
import time
import json
import google.generativeai as genai
import traceback
import sys
import argparse
import hashlib
import re


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FileUploadAnalyzer:
    def __init__(self, upload_folder=None, api_key=None):
        # Base upload configuration
        self.BASE_UPLOAD_FOLDER = upload_folder or os.path.join(os.path.expanduser("~"), "Documents", "HauntAI_Uploads")
        self.TEMP_UPLOAD_FOLDER = os.path.join(self.BASE_UPLOAD_FOLDER, "temp")
        self.MAX_CONTENT_LENGTH = 1024 * 1024 * 1024
        self.CHUNK_SIZE = 1024 * 1024 * 10
        
        # Strictly define allowed file extensions
        self.ALLOWED_EXTENSIONS = {'.py', '.js', '.env', '.json', '.php', '.yaml', '.yml', '.ts'}

        # Create necessary directories
        os.makedirs(self.BASE_UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(self.TEMP_UPLOAD_FOLDER, exist_ok=True)
        
        # Upload status tracking
        self.upload_status = {
            "uploaded": False,
            "analyzed": False,
            "current_session": None,
            "files_processed": 0,
            "chunks_processed": {},
        }

        # Configure Gemini API
        self.GEMINI_API_KEY = api_key or os.environ.get("GEMINI_API_KEY", "AIzaSyDUkFwxDyAUbEZzemd4HNitryyacbL0QBI")
        genai.configure(api_key=self.GEMINI_API_KEY)

    def _is_allowed_file(self, filepath):
        filename = os.path.basename(filepath).lower()
        name, ext = os.path.splitext(filename)
        return (
            ext in self.ALLOWED_EXTENSIONS or
            filename == '.env' or
            filename.startswith('.env.')
        )


    def _hash_file(self, filepath):
        """Generate a hash for a file to check for duplicates"""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()

    def add_line_numbers_to_file(self, file_path, dest_filepath):
        """Baca file, tambahkan nomor baris, dan simpan ke file baru."""
        try:
            with open(file_path, 'r', encoding='utf-8') as src_file:
                lines = src_file.readlines()
            
            with open(dest_filepath, 'w', encoding='utf-8') as dest_file:
                for line_number, line in enumerate(lines, 1):
                    # Menambahkan nomor baris di awal setiap baris, menjaga indentasi dan format
                    dest_file.write(f"{line_number:4}: {line}")  # Format 4 digit untuk nomor baris
            logger.info(f"Added line numbers to {file_path} and saved to {dest_filepath}")
        except Exception as e:
            logger.error(f"Error adding line numbers to {file_path}: {str(e)}")
            raise
    
    def generate_pdf_report(self, analysis_result, output_path):
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import cm, inch
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import Color

        def draw_watermark(canvas_obj, doc):
            canvas_obj.saveState()
            canvas_obj.setFont("Helvetica-Bold", 100)
            canvas_obj.setFillColor(Color(0, 0, 0.33, alpha=0.08))  # Transparan navy
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
                bottomMargin=2 * cm
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

            # Judul dan waktu
            elements.append(Paragraph(f"Security Analysis Report - {analysis_result['filename']}", title_style))
            elements.append(Spacer(1, 0.25 * cm))
            elements.append(Paragraph(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", left_style))
            elements.append(Spacer(1, 0.75 * cm))

            if analysis_result['status'] == 'not_found':
                elements.append(Paragraph("No sensitive information found in this file.", body_style))
            elif analysis_result['status'] == 'error':
                elements.append(Paragraph(f"Error during analysis: {analysis_result.get('error', 'Unknown error')}", body_style))
            else:
                for chunk_result in analysis_result.get('analysis_results', []):
                    if chunk_result.get('status') == 'success':
                        if len(analysis_result.get('analysis_results', [])) > 1:
                            elements.append(Paragraph(f"Chunk {chunk_result.get('chunk', 1)}", subtitle_style))
                            elements.append(Spacer(1, 0.25 * cm))

                        result_text = chunk_result.get('result', '')
                        table_data = self._extract_table_data(result_text)

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

                            explanations = self._extract_explanations(result_text)
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
                        error_msg = f"Error analyzing chunk {chunk_result.get('chunk', 1)}: {chunk_result.get('error', 'Unknown error')}"
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
        
        seen = set()
        deduplicated_table = []
        for row in table_data:
            line_number = row[2]
            snippet = row[3]
            key = (line_number, snippet)
            if key not in seen:
                seen.add(key)
                deduplicated_table.append(row)
        
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
    
    

    def post_process_analysis_result(self, analysis_result):
        """
        Filter out false positives using predefined patterns (ignore patterns).

        :param analysis_result: Raw result from AI analysis
        :return: Cleaned analysis result with ignored patterns removed or None if no sensitive data found
        """
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
        
        # Combine all patterns into one regex pattern
        combined_pattern = '|'.join(ignore_patterns)
        
        # Process the entire analysis result line by line
        lines = analysis_result.split('\n')
        filtered_lines = []
        removed_types = []
        remaining_types = set()  # Track types that remain in the table
        in_header = True

        seen_combinations = set()
        
        # First pass: identify what vulnerability types are present and which ones get filtered
        for line in lines:
            # Check if this is a table data row (has pipe character and not a header)
            if '|' in line and not in_header and not re.match(r'\|[-\s|]+\|', line) and not re.match(r'\|\s*Type\s*\|', line, re.IGNORECASE):
                # Extract the vulnerability type
                type_match = re.search(r'\|\s*(.*?)\s*\|', line)
                if type_match:
                    vuln_type = type_match.group(1).strip()
                    base_type = vuln_type.split(':')[0].strip() if ':' in vuln_type else vuln_type
                    
                    # Extract line number and snippet (columns 3 and 4)
                    parts = [part.strip() for part in line.split('|')]
                    if len(parts) >= 5:  # Ensure we have enough columns
                        line_number = parts[3]  # Line number column
                        snippet = parts[4]      # Snippet column
                        
                        # ONLY check the line number and snippet against patterns
                        combined_text = f"{line_number} {snippet}"
                        
                        if re.search(combined_pattern, combined_text):
                            # This line matches a filter pattern
                            removed_types.append(vuln_type)
                        else:
                            # This line doesn't match a filter pattern and will remain
                            remaining_types.add(base_type)
            elif re.match(r'\|[-\s|]+\|', line):
                in_header = False
        
        # Reset variables for second pass
        in_header = True
        
        # Second pass: filter out the lines
        for line in lines:
            # Check if this is a table data row
            if '|' in line:
                if re.match(r'\|[-\s|]+\|', line) or re.match(r'\|\s*Type\s*\|', line, re.IGNORECASE):
                    # This is a table header or separator line
                    filtered_lines.append(line)
                    if re.match(r'\|[-\s|]+\|', line):
                        in_header = False
                elif not in_header:
                    # This is a table data row
                    parts = [part.strip() for part in line.split('|')]
                    if len(parts) >= 5:  # Ensure we have enough columns
                        line_number = parts[3]  # Line number column
                        snippet = parts[4]      # Snippet column
                        
                        # Create unique key for this line number + snippet combination
                        unique_key = f"{line_number}|{snippet}"
                        
                        # Only check against line number and snippet
                        combined_text = f"{line_number} {snippet}"
                        
                        # Keep line if it doesn't match any pattern AND isn't a duplicate
                        if not re.search(combined_pattern, combined_text) and unique_key not in seen_combinations:
                            filtered_lines.append(line)
                            seen_combinations.add(unique_key)
            else:
                # Non-table line (headings, explanations, etc.)
                filtered_lines.append(line)
        
        # If no table data rows are left after filtering, return None
        table_data_rows = [line for line in filtered_lines if '|' in line and not re.match(r'\|[-\s|]+\|', line) 
                        and not re.match(r'\|\s*Type\s*\|', line, re.IGNORECASE)]
        if not table_data_rows:
            return None
        
        # Filter reason sections, but only for vulnerability types that don't have any
        # representatives left in the table
        intermediate_result = '\n'.join(filtered_lines)
        cleaned_result = intermediate_result
        
        # Find vulnerability types that need to have their reason sections removed
        # (those that were completely removed and don't have a base type remaining)
        types_to_remove = []
        for vuln_type in removed_types:
            base_type = vuln_type.split(':')[0].strip() if ':' in vuln_type else vuln_type
            if base_type not in remaining_types:
                types_to_remove.append(vuln_type)
        
        # Remove reason sections only for types that were completely removed
        if types_to_remove:
            for vuln_type in types_to_remove:
                base_type = vuln_type.split(':')[0].strip()
                escaped = re.escape(base_type)
                
                # Only remove if we're sure this base type has no representatives
                if base_type not in remaining_types:
                    # Pattern to match numbered vulnerability explanations
                    pattern = rf"\d+\.\s+\*\*{escaped}\*\*:.*?(?=\n\d+\.\s+\*\*|\Z)"
                    cleaned_result = re.sub(pattern, "", cleaned_result, flags=re.DOTALL).strip()
                    
                    # Alternative pattern to catch variants in formatting
                    alt_pattern = rf"\*\*{escaped}\*\*:.*?(?=\n\*\*|\Z)"
                    cleaned_result = re.sub(alt_pattern, "", cleaned_result, flags=re.DOTALL).strip()
        
        # Log the filtered out parts
        if cleaned_result != analysis_result:
            if types_to_remove:
                logger.info(f"[POST_PROCESS] Filtered out vulnerability types: {', '.join(types_to_remove)}")
            
            removed_content = []
            for pattern in ignore_patterns:
                matches = re.findall(pattern, analysis_result)
                if matches:
                    removed_content.append(f"Pattern {pattern} removed: {matches[:5]}...") 
            if removed_content:
                logger.info("[POST_PROCESS] Berikut adalah pattern yang berhasil memfilter baris:")
                for pattern in ignore_patterns:
                    matches = re.findall(pattern, analysis_result)
                    if matches:
                        logger.info(f"[FILTER] Pattern: {pattern}")
                        for example in matches[:3]:
                            logger.info(f"    → {example}")
                        if len(matches) > 5:
                            logger.info(f"    ...and {len(matches) - 5} more lines")
        
        return cleaned_result

    def _format_size(self, size_bytes):
        if size_bytes >= 1024**3:  # GB
            return f"{size_bytes / 1024**3:.2f} GB"
        elif size_bytes >= 1024**2:  # MB
            return f"{size_bytes / 1024**2:.2f} MB"
        elif size_bytes >= 1024:  # KB
            return f"{size_bytes / 1024:.2f} KB"
        else:
            return f"{size_bytes} B"
    
    def upload_file_chunked(self, file_path, dest_path):
        """
        Upload a file in multiple chunks, save chunks to temp folder,
        then merge into dest_path.
        """
        try:
            file_id = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            size_label = self._format_size(file_size)

            if file_size <= 30 * 1024 * 1024:  
                shutil.copyfile(file_path, dest_path)
                logger.info(f"[Copy] File size {size_label} — copied directly without chunking.")
                return True

            total_chunks = (file_size + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE
            logger.info(f"[Chunk] Uploading {file_id} → {total_chunks} chunks (~{size_label})")

            chunk_paths = []
            with open(file_path, 'rb') as src_file:
                for idx in range(total_chunks):
                    chunk = src_file.read(self.CHUNK_SIZE)
                    chunk_filename = f"{file_id}.{idx:03d}.part"
                    chunk_path = os.path.join(self.TEMP_UPLOAD_FOLDER, chunk_filename)

                    os.makedirs(self.TEMP_UPLOAD_FOLDER, exist_ok=True)
                    with open(chunk_path, 'wb') as chunk_file:
                        chunk_file.write(chunk)

                    chunk_paths.append(chunk_path)
                    logger.info(f"[Chunk] Saved: {chunk_path}")

            # Gabungkan semua chunk
            with open(dest_path, 'wb') as final_file:
                for chunk_path in chunk_paths:
                    with open(chunk_path, 'rb') as part:
                        shutil.copyfileobj(part, final_file)

            logger.info(f"[Chunk] Merged chunks into: {dest_path}")

            # Hapus file chunk setelah merge
            for chunk_path in chunk_paths:
                try:
                    os.remove(chunk_path)
                    logger.info(f"[Chunk] Deleted: {chunk_path}")
                except Exception as e:
                    logger.warning(f"[Chunk] Failed to delete {chunk_path}: {e}")

            self.upload_status["chunks_processed"][file_id] = {
                "total_chunks": total_chunks,
                "processed_chunks": total_chunks,
                "status": "complete"
            }

            return True

        except Exception as e:
            logger.error(f"[Chunk Upload Error] {e}")
            return False
        
    def split_file_into_chunks(self, file_path, chunk_size=10000):
        chunk_paths = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

            total_chunks = (len(lines) + chunk_size - 1) // chunk_size  # Calculate number of chunks
            file_name = os.path.basename(file_path)
            base_name, ext = os.path.splitext(file_name)

            # Split lines into chunks and save each chunk as a separate file
            for i in range(total_chunks):
                chunk_file_path = os.path.join(self.TEMP_UPLOAD_FOLDER, f"{base_name}_chunk_{i + 1}{ext}")
                chunk_lines = lines[i * chunk_size: (i + 1) * chunk_size]  # Get the lines for this chunk

                with open(chunk_file_path, 'w', encoding='utf-8') as chunk_file:
                    chunk_file.writelines(chunk_lines)

                chunk_paths.append(chunk_file_path)
                logger.info(f"Created chunk: {chunk_file_path}")

            return chunk_paths
        except Exception as e:
            logger.error(f"Error while splitting file: {str(e)}")
            return []


    def analyze_file_with_gemini(self, file_path, analysis_prompt):
        """Analyze a file's content using Google's Gemini API"""
        try:
            # Normalize file path to handle Windows backslashes
            file_path = os.path.normpath(file_path)
            filename = os.path.basename(file_path)
            logger.info(f"[ANALYSIS] Starting analysis for {filename} at path: {file_path}")

            # Read the content of the file
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                file_content = f.read()

            lines = file_content.splitlines()  # Create a list of lines for line count
            logger.info(f"[ANALYSIS] Successfully read {filename}, size: {len(file_content)} chars and {len(lines)} lines")

            # Split the file into chunks if it's larger than 10,000 lines
            chunk_paths = self.split_file_into_chunks(file_path) if len(lines) > 10000 else [file_path]
            
            # Process each chunk
            analysis_results = []
            for idx, chunk_path in enumerate(chunk_paths):
                try:
                    # Read the content from the chunk (instead of the full file)
                    with open(chunk_path, 'r', encoding='utf-8', errors='replace') as chunk_file:
                        chunk_content = chunk_file.read()

                    # Prepare the prompt with only the chunk content
                    prompt = f"""
                    Analyze this code file thoroughly:

                    Filename: {filename}

                    CODE CONTENT:
                    ```
                    {chunk_content}
                    ```

                    {analysis_prompt}
                    ### **TASK : Detect all sensitive data that is hardcoded based on below ** 
                    **Confirm by replying only with the detected sensitive data and its type. Do not explain unless asked.**

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
                    if chunk_path == file_path:
                        logger.info(f"[FILE_ANALYSIS] Sending {filename} to Gemini API for analysis")
                    else:
                        logger.info(f"[CHUNK_ANALYSIS] Sending chunk {idx+1} of {filename} to Gemini API for analysis")

                    # Send to Gemini API
                    model = genai.GenerativeModel("gemini-2.0-flash")
                    response = model.generate_content(prompt)

                    if not response.text:
                        if chunk_path == file_path:
                            logger.error(f"[FILE_ANALYSIS_ERROR] Empty response from Gemini API for {filename}")
                        else:
                            logger.error(f"[CHUNK_ANALYSIS_ERROR] Empty response from Gemini API for chunk {idx+1} of {filename}")
                        analysis_results.append({"filename": filename, "chunk": idx+1, "status": "error", "error": "Empty response from Gemini API"})
                    else:
                        # Process the result (filtering sensitive data)
                        filtered_result = self.post_process_analysis_result(response.text)  # This is the part that filters based on predefined patterns

                        if filtered_result is None:
                            if chunk_path == file_path:
                                logger.info(f"[FILE_ANALYSIS] No sensitive information found in {filename}")
                            else:
                                logger.info(f"[CHUNK_ANALYSIS] No sensitive information found in chunk {idx+1} of {filename}")
                            continue


                        # Save the result for this chunk
                        result_data = {
                            "filename": filename,
                            "chunk": idx+1,
                            "status": "success",
                            "result": filtered_result
                        }

                        analysis_results.append(result_data)


                except Exception as e:
                    if chunk_path == file_path:
                        logger.error(f"[FILE_ANALYSIS_ERROR] Failed to analyze {filename}: {str(e)}")
                    else:
                        logger.error(f"[CHUNK_ANALYSIS_ERROR] Failed to analyze chunk {idx+1} of {filename}: {str(e)}")
                    analysis_results.append({"filename": filename, "chunk": idx+1, "status": "error", "error": f"Chunk analysis error: {str(e)}"})

                # Delay between API calls to avoid rate limiting
                time.sleep(10)
                
            
            successful_chunks = [chunk for chunk in analysis_results if chunk['status'] == 'success']
            # Return the results
            if successful_chunks:
                output_pdf_path = os.path.join(self.upload_status["current_session"], "analysis", f"{os.path.splitext(filename)[0]}_report.pdf")
                combined_result = {
                    "filename": filename,
                    "status": "success",
                    "analysis_results": successful_chunks
                }
                self.generate_pdf_report(combined_result, output_pdf_path)


                logger.info(f"[ANALYSIS] Completed analysis for {filename} with {len(analysis_results)} results")
                return {"filename": filename, "status": "success", "analysis_results": analysis_results}
            else:
                logger.info(f"[ANALYSIS] No sensitive information found in {filename}")
                return {"filename": filename, "status": "not_found", "message": "No sensitive information found"}


        except Exception as e:
            logger.error(f"[ANALYSIS_ERROR] Failed to analyze {file_path}: {str(e)}")
            traceback.print_exc()  # Print stack trace for debugging
            return {"filename": os.path.basename(file_path), "status": "error", "error": str(e)}
        

    def upload_and_analyze_file(self, file_path):
        """
        Upload and analyze a single file with strict filtering
        
        :param file_path: Path to the file to analyze
        """
        # Validate file
        if not os.path.isfile(file_path):
            logger.error(f"Specified path is not a file: {file_path}")
            return False
        
        # Check file extension
        if not self._is_allowed_file(file_path):
            logger.error(f"File type not allowed: {file_path}")
            return False
        
        # Create session folder
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        session_folder = os.path.join(self.BASE_UPLOAD_FOLDER, timestamp)
        os.makedirs(session_folder, exist_ok=True)
        analysis_folder = os.path.join(session_folder, "analysis")
        files_folder = os.path.join(session_folder, "files")
        
        os.makedirs(analysis_folder, exist_ok=True)
        os.makedirs(files_folder, exist_ok=True)
        
        # Update upload status
        self.upload_status["current_session"] = session_folder
        self.upload_status["uploaded"] = True
        
        # Copy file to session's files folder with line numbers added
        filename = os.path.basename(file_path)
        dest_filepath = os.path.join(files_folder, filename)

        # Use chunked upload instead of direct copy
        upload_success = self.upload_file_chunked(file_path, dest_filepath)
        if not upload_success:
            logger.error(f"Failed to upload file: {file_path}")
            return False

        # Add line numbers before saving to the folder
        self.add_line_numbers_to_file(dest_filepath,  dest_filepath)
        
        # Analyze file
        analysis_prompt = """Analyze this code file thoroughly for sensitive information and security vulnerabilities."""
        # Delay 10 seconds before making the API call to avoid rate limits
        time.sleep(10)
        result = self.analyze_file_with_gemini(dest_filepath, analysis_prompt)
        
        # Log results
        if result['status'] == 'success':
            logger.info(f"Sensitive information found in {filename}")
        elif result['status'] == 'not_found':
            logger.info(f"No sensitive information found in {filename}")
        else:
            logger.error(f"Error analyzing {filename}: {result.get('error', 'Unknown error')}")
        
        # Update status
        self.upload_status["analyzed"] = True
        self.upload_status["files_processed"] = 1
        
        return result

    def upload_and_analyze_folder(self, folder_path):
        """
        Upload and analyze files with strict filtering
        
        :param folder_path: Path to the folder containing files to analyze
        """
        # Validate folder
        if not os.path.isdir(folder_path):
            logger.error(f"Specified path is not a directory: {folder_path}")
            return False
        
        # Create session folder
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        session_folder = os.path.join(self.BASE_UPLOAD_FOLDER, timestamp)
        os.makedirs(session_folder, exist_ok=True)
        analysis_folder = os.path.join(session_folder, "analysis")
        files_folder = os.path.join(session_folder, "files")
        
        os.makedirs(analysis_folder, exist_ok=True)
        os.makedirs(files_folder, exist_ok=True)
        
        # Update upload status
        self.upload_status["current_session"] = session_folder
        self.upload_status["uploaded"] = True
        
        # Collect files to analyze
        files_to_analyze = []
        processed_hashes = set()
        
        # Walk through directory and filter files
        for root, _, files in os.walk(folder_path):
            for file in files:
                filepath = os.path.join(root, file)
                
                # Strict file extension filtering
                if self._is_allowed_file(filepath):
                    # Check for duplicates using hash
                    file_hash = self._hash_file(filepath)
                    if file_hash not in processed_hashes:
                        # Buat nama unik dengan struktur path relatif
                        rel_path = os.path.relpath(filepath, folder_path)
                        safe_filename = rel_path.replace(os.sep, "__")  # Contoh: subdir/index.js -> subdir__index.js
                        dest_filepath = os.path.join(files_folder, safe_filename)

                        # Use chunked upload instead of direct copy
                        upload_success = self.upload_file_chunked(filepath, dest_filepath)
                        if upload_success:
                            # Add line numbers to a new file
                            numbered_filepath = dest_filepath
                            self.add_line_numbers_to_file(dest_filepath, numbered_filepath)
                            files_to_analyze.append(numbered_filepath)
                            processed_hashes.add(file_hash)
                        else:
                            logger.error(f"Failed to upload file: {filepath}")
                else:
                    logger.info(f"Skipping file (not allowed): {filepath}")
        
        logger.info(f"Found {len(files_to_analyze)} files to analyze")
        
        # Analyze files
        analysis_results = []
        for idx, filepath in enumerate(files_to_analyze, 1):
            logger.info(f"Analyzing file {idx}/{len(files_to_analyze)}: {filepath}")
            
            analysis_prompt = """Analyze this code file thoroughly for sensitive information and security vulnerabilities."""
            
            result = self.analyze_file_with_gemini(filepath, analysis_prompt)
            analysis_results.append(result)
            
            # Delay between API calls to avoid rate limiting
            time.sleep(10)
        
        # Collect the results
        successful_files = [r['filename'] for r in analysis_results if r['status'] == 'success']
        error_files = [r for r in analysis_results if r['status'] == 'error']
        skipped_files = [r for r in analysis_results if r['status'] == 'skipped']
        
        logger.info(f"Analysis complete. Success: {len(successful_files)}, Errors: {len(error_files)}, Skipped: {len(skipped_files)}")
        
        # Log any errors in detail
        for error in error_files:
            logger.error(f"[ANALYSIS_ERROR] {error['filename']}: {error.get('error', 'Unknown error')}")
        
        # Update status
        self.upload_status["analyzed"] = True
        self.upload_status["files_processed"] = len(successful_files)
        
        # Generate summary report
        summary_path = os.path.join(session_folder, "analysis_summary.json")

        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump({
                "total_files_analyzed": len(files_to_analyze),
                "files_with_sensitive_info": len(successful_files),
                "files_with_errors": len(error_files),
                "skipped_files": len(skipped_files),
                "results": analysis_results
            }, f, indent=2)
        
        logger.info(f"Analysis complete. Summary saved to {summary_path}")
        return True

def main():
    parser = argparse.ArgumentParser(description="Command-line File Upload and Analysis Tool")
    parser.add_argument("path", help="Path to the file or folder to analyze")
    parser.add_argument("--api-key", help="Gemini API key (optional if GEMINI_API_KEY env var is set)")
    parser.add_argument("--upload-folder", help="Custom upload folder path")
    
    args = parser.parse_args()
    
    try:
        analyzer = FileUploadAnalyzer(
            upload_folder=args.upload_folder, 
            api_key=args.api_key
        )
        
        # Cek apakah path adalah file atau folder
        if os.path.isfile(args.path):
            success = analyzer.upload_and_analyze_file(args.path)
        elif os.path.isdir(args.path):
            success = analyzer.upload_and_analyze_folder(args.path)
        else:
            logger.error(f"Invalid path: {args.path}")
            sys.exit(1)
        
        sys.exit(0 if success else 1)
    
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()