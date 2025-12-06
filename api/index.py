from http.server import BaseHTTPRequestHandler
import google.generativeai as genai
import base64
import json
import os
import re

# Konfigurasi Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# PROMPT GEMINI UNTUK ANALISIS MAKANAN
# ==========================================
FOOD_ANALYSIS_PROMPT = """
Kamu adalah ahli gizi Indonesia yang sangat ketat dan HANYA menggunakan data resmi dari Kementerian Kesehatan Republik Indonesia, yaitu:
- TKPI (Tabel Komposisi Pangan Indonesia) edisi terbaru
- DKBM (Daftar Komposisi Bahan Makanan)

INSTRUKSI WAJIB:
1. Identifikasi makanan dalam foto dengan teliti
2. Estimasi porsi berdasarkan tampilan visual
3. Hitung nilai gizi HANYA berdasarkan referensi TKPI/DKBM
4. Jika makanan terdiri dari beberapa bahan, jumlahkan nilai gizi masing-masing komponen
5. Berikan tingkat kesegaran berdasarkan tampilan visual (warna, tekstur, kondisi)

REFERENSI NILAI GIZI TKPI/DKBM (per 100 gram kecuali disebutkan lain):
- Nasi putih: 175 kkal, protein 3.0g, lemak 0.3g, karbo 39.8g
- Nasi goreng (dengan minyak): 180-200 kkal per 100g
- Telur ayam rebus (1 butir 50g): 75 kkal, protein 6.3g, lemak 5.3g, karbo 0.6g
- Telur ceplok/goreng (1 butir): 110 kkal, protein 6.5g, lemak 8.5g, karbo 0.6g
- Tempe goreng: 210 kkal, protein 18.3g, lemak 11.4g, karbo 9.4g
- Tempe rebus: 150 kkal, protein 18.3g, lemak 4.0g, karbo 9.4g
- Tahu goreng: 115 kkal, protein 10.9g, lemak 5.0g, karbo 4.0g
- Ayam goreng (dengan kulit): 245 kkal, protein 25.0g, lemak 15.0g, karbo 0g
- Ayam goreng (tanpa kulit): 190 kkal, protein 27.0g, lemak 8.0g, karbo 0g
- Daging sapi rendang: 193 kkal, protein 22.6g, lemak 9.5g, karbo 4.0g
- Sayur bayam rebus: 23 kkal, protein 2.3g, lemak 0.3g, karbo 3.2g
- Sayur kangkung: 29 kkal, protein 3.0g, lemak 0.3g, karbo 5.4g
- Ikan bandeng goreng: 170 kkal, protein 20.0g, lemak 10.0g, karbo 0g
- Ikan lele goreng: 175 kkal, protein 18.0g, lemak 11.0g, karbo 0g
- Sambal: 30 kkal per sendok makan
- Kerupuk (5 keping): 80 kkal, lemak 3.0g, karbo 12.0g
- Mie goreng: 220 kkal, protein 5.0g, lemak 9.0g, karbo 32.0g
- Soto ayam (1 mangkuk): 150-200 kkal
- Gado-gado (1 porsi): 300-400 kkal
- Sate ayam (10 tusuk): 250-300 kkal
- Bakso (1 mangkuk dengan mie): 350-450 kkal

KRITERIA TINGKAT KESEGARAN:
- 80-100%: Makanan terlihat sangat segar, warna cerah, tidak ada tanda pembusukan
- 60-79%: Makanan cukup segar, sedikit perubahan warna minor
- 40-59%: Makanan mulai kurang segar, ada perubahan warna/tekstur
- 0-39%: Makanan tidak segar, terlihat basi atau rusak

Dari foto makanan ini, analisis dan kembalikan HANYA dalam format JSON berikut (tanpa markdown, tanpa penjelasan tambahan):

{
  "nama_makanan": "Nama lengkap makanan dalam Bahasa Indonesia",
  "porsi_standar": "Deskripsi porsi (contoh: 1 porsi (200 gram))",
  "kalori": [nilai numerik tanpa satuan],
  "protein": [nilai numerik tanpa satuan],
  "lemak": [nilai numerik tanpa satuan],
  "karbohidrat": [nilai numerik tanpa satuan],
  "freshness_percentage": [nilai 0-100],
  "saran_singkat": "Saran konsumsi dalam 1-2 kalimat bahasa Indonesia yang natural"
}

PENTING: Kembalikan HANYA JSON valid tanpa teks tambahan apapun.
"""

# ==========================================
# PROMPT GEMINI UNTUK SARAN HARIAN PERSONAL
# ==========================================
DAILY_SUGGESTION_PROMPT = """
Kamu adalah ahli gizi Indonesia yang ramah dan memberikan saran personal berdasarkan data asupan gizi harian.

DATA PENGGUNA:
- Nama: {nama}
- Kebutuhan Kalori Harian (BMR): {bmr} kkal
- Total Asupan Hari Ini:
  • Kalori: {total_kalori} kkal ({persen_kalori}% dari BMR)
  • Protein: {total_protein} g
  • Lemak: {total_lemak} g
  • Karbohidrat: {total_karbohidrat} g

PEDOMAN GIZI SEIMBANG KEMENKES RI:
- Karbohidrat: 45-65% dari total kalori
- Protein: 10-15% dari total kalori (0.8-1g per kg BB)
- Lemak: 20-35% dari total kalori

INSTRUKSI:
1. Analisis apakah asupan sudah seimbang atau belum
2. Berikan saran yang personal, gunakan nama pengguna
3. Rekomendasikan makanan Indonesia yang spesifik untuk melengkapi kebutuhan
4. Gunakan bahasa Indonesia yang natural dan ramah
5. Maksimal 3-4 kalimat

Berikan saran dalam format teks biasa (bukan JSON), langsung ke poin tanpa pembuka.
"""


def extract_json_from_response(text):
    """Ekstrak JSON dari response Gemini yang mungkin mengandung markdown"""
    # Coba parse langsung
    try:
        return json.loads(text)
    except:
        pass
    
    # Coba ekstrak dari code block
    json_match = re.search(r'``````', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except:
            pass
    
    # Coba cari JSON object dalam text
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except:
            pass
    
    return None


@app.route('/api/analyze', methods=['POST'])
def analyze_food():
    try:
        data = request.get_json()
        image_base64 = data.get('image')
        
        if not image_base64:
            return jsonify({'error': 'Gambar tidak ditemukan'}), 400
        
        # Decode base64 image
        image_data = base64.b64decode(image_base64)
        
        # Konfigurasi model Gemini
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Buat request dengan gambar
        response = model.generate_content([
            FOOD_ANALYSIS_PROMPT,
            {
                'mime_type': 'image/jpeg',
                'data': image_data
            }
        ])
        
        # Parse response
        result_text = response.text.strip()
        result = extract_json_from_response(result_text)
        
        if result is None:
            return jsonify({
                'error': 'Gagal memproses respons AI',
                'raw_response': result_text
            }), 500
        
        # Validasi dan sanitasi hasil
        required_fields = ['nama_makanan', 'porsi_standar', 'kalori', 'protein', 
                         'lemak', 'karbohidrat', 'freshness_percentage', 'saran_singkat']
        
        for field in required_fields:
            if field not in result:
                if field in ['kalori', 'protein', 'lemak', 'karbohidrat']:
                    result[field] = 0
                elif field == 'freshness_percentage':
                    result[field] = 85
                elif field == 'nama_makanan':
                    result[field] = 'Makanan Tidak Dikenali'
                elif field == 'porsi_standar':
                    result[field] = '1 porsi'
                else:
                    result[field] = ''
        
        # Pastikan nilai numerik
        for field in ['kalori', 'protein', 'lemak', 'karbohidrat']:
            try:
                result[field] = float(result[field])
            except:
                result[field] = 0
        
        try:
            result['freshness_percentage'] = int(result['freshness_percentage'])
            result['freshness_percentage'] = max(0, min(100, result['freshness_percentage']))
        except:
            result['freshness_percentage'] = 85
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/suggest', methods=['POST'])
def get_daily_suggestion():
    try:
        data = request.get_json()
        
        total_kalori = data.get('total_kalori', 0)
        total_protein = data.get('total_protein', 0)
        total_lemak = data.get('total_lemak', 0)
        total_karbohidrat = data.get('total_karbohidrat', 0)
        bmr = data.get('bmr', 2000)
        nama = data.get('nama', 'Pengguna')
        
        # Hitung persentase dari BMR
        persen_kalori = round((total_kalori / bmr) * 100, 1) if bmr > 0 else 0
        
        # Format prompt dengan data pengguna
        prompt = DAILY_SUGGESTION_PROMPT.format(
            nama=nama,
            bmr=round(bmr),
            total_kalori=round(total_kalori),
            persen_kalori=persen_kalori,
            total_protein=round(total_protein, 1),
            total_lemak=round(total_lemak, 1),
            total_karbohidrat=round(total_karbohidrat, 1)
        )
        
        # Generate saran
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        
        saran = response.text.strip()
        
        return jsonify({'saran': saran})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'NutriScan API berjalan dengan baik',
        'version': '1.0.0'
    })

def handler(request, *_):
    return app(request)

