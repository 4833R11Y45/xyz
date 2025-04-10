python3.8 -m pip install -r requirements.txt
python3.8 -m spacy download
apt-get update && apt-get install tesseract-ocr -y
apt-get install poppler-utils -y
# apt-get install libreoffice-writer libreoffice-pdfimport --no-install-recommends -y
#pytest -v
gunicorn --bind=0.0.0.0 --timeout 3000 app:app