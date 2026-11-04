# Componenti di terze parti

Questa distribuzione utilizza componenti con licenze proprie; il codice sorgente dell'applicazione accompagna l'eseguibile nel progetto `doc_anon`. Non è stata acquistata una licenza commerciale di PyMuPDF o Qt per questo progetto.

| Componente | Provenienza / licenza |
| --- | --- |
| Rizzo: rilevatori di formati | Rizzo AI Academy, Simone Rizzo, MIT. Revisione `30d6f9c675e245bc8494df959adaeaa9d8de35c7`. Testo completo in `vendor/RIZZO-LICENSE.txt`. |
| Modello Rizzo 0.3B v1.5.0 | `rizzoaiacademy/rizzo-pii-0.3B`, revisione `a1c3c83827eca22e9675e30c1111c4641caf5901`; scheda modello dichiara MIT. Scaricato separatamente, non incluso nello ZIP. |
| PyMuPDF / MuPDF | Artifex Software, GNU AGPL v3 oppure licenza commerciale. Testi forniti dal pacchetto in `vendor/licenses`. |
| PySide6 / Qt / Shiboken | The Qt Company, distribuzione open source con LGPL v3 / GPL secondo i componenti. Librerie dinamiche; testi forniti dal pacchetto in `vendor/licenses`. |
| PyTorch CPU | Licenza BSD e licenze dei componenti inclusi; testi forniti dal pacchetto in `vendor/licenses`. |
| Transformers / Tokenizers | Hugging Face, Apache 2.0; testi forniti dai pacchetti in `vendor/licenses`. |
| Tesseract / tessdata_fast italiano | Tesseract contributors, Apache 2.0. Binari Windows UB Mannheim; DLL dipendenti mantengono le proprie licenze. Documentazione inclusa in `vendor/tesseract/doc`. |
| Python | Python Software Foundation License. |
| Manrope / Newsreader | Font inclusi da Google Fonts; SIL Open Font License 1.1. Testi in `assets/fonts/*-OFL.txt`. |
| PyInstaller | GPL con eccezione per la distribuzione dei programmi generati. |

Il file `doc_anon/rizzo_detectors.py` è copiato senza modifiche dalla revisione indicata. Il codice di lettura, OCR e rendering deriva da Level DOCS ed è stato adattato per l'uso desktop. Le copie esportate non includono componenti software.

La distribuzione esterna va accompagnata da sorgenti e avvisi applicabili alle dipendenze; questa cartella conserva il progetto modificabile e gli script di build.
