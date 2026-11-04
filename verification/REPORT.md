# Verifica del 4 novembre 2026

Versione: Doc Anon 0.1.0, Windows x64.

## Test automatizzati

`python -m pytest tests -q`: **15 test superati**. Ambiente Python 3.12.10 su Windows 11, PyTorch 2.10.0 CPU, PyMuPDF 1.27.1 e PySide6 Essentials 6.10.2. Le sole segnalazioni erano avvisi di deprecazione interni a PyTorch.

Copertura: rimozione del testo e dei pixel oscurati nelle copie; assenza di allegati e metadati originali; esportazioni senza sovrascrittura; ripulitura in caso di errore; geometrie non valide; coordinate su PDF ruotati e ritagliati; rimozione e aggiunta di aree; modifica iniziali e dimensioni nell'interfaccia; annullamento; download riprendibile; rifiuto di download danneggiati; risorse mancanti senza download impliciti.

La prova con modello reale comprende PDF nativo e scansione sintetica, caricamento del modello da disco, OCR italiano, riconoscimento di nome/email ed esportazione, con connessioni di rete e DNS bloccati nel processo Python.

## Eseguibile compilato

PyInstaller 6.19.0 ha prodotto `dist/DocAnon/DocAnon.exe` e le dipendenze nella cartella `_internal`. Il test dell'eseguibile, senza utilizzare l'interprete dell'ambiente di sviluppo, ha restituito:

```json
{
  "ok": true,
  "frozen": true,
  "network_attempts": 0,
  "native_areas": 3,
  "scanned_areas": 3,
  "bundled_ocr": true,
  "seconds": 25.44
}
```

Il test include anche l'interfaccia Qt, le risorse grafiche incorporate e la creazione delle due copie per entrambi i documenti sintetici. Le anteprime `welcome.png` e `review.png` sono prodotte dal programma compilato. Nessun documento reale dell'utente è stato utilizzato.

## Limiti della verifica

Il test è stato eseguito sul computer di sviluppo, non su una macchina virtuale Windows pulita. Il blocco della rete è applicato alle connessioni socket e al DNS del processo durante le prove; non è una certificazione del sistema operativo. Il riconoscimento automatico non garantisce la scoperta di tutti i dati personali. La revisione visiva resta parte del flusso di lavoro.

Lo ZIP non contiene il modello: il download iniziale è avviato esplicitamente dall'utente. Il downloader reale è stato eseguito con successo e ha verificato tutti i file del modello e dell'OCR. La firma digitale dell'eseguibile non è presente.

## Installer Windows

Creato `dist/DocAnon-Setup-0.1.0-x64.exe` con Inno Setup 7.1.1 x64: 211.061.156 byte. Il compilatore proviene dalla release ufficiale `jrsoftware/issrc/is-7_1_1`; il download è stato verificato tramite SHA-256 `8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0` e firma Authenticode valida di Pyrsys B.V.

`scripts/test-installer.ps1` ha verificato il pacchetto reale in una nuova directory di prova, senza lasciare Doc Anon installato:

- Installazione per utente, registrazione nella lista delle app e collegamento Start con destinazione corretta.
- Reinstallazione sulla stessa cartella e confronto SHA-256 di tutti i 4.665 file del payload, più verifica delle istruzioni specifiche per l'app installata.
- Avvio dell'eseguibile installato con il modello reale e l'OCR incluso: 3 aree rilevate sul PDF sintetico, 3 sulla scansione, esportazione di entrambe le copie e caricamento dell'interfaccia. Zero tentativi di connessione; prova completata in 7,62 secondi.
- Disinstallazione riuscita: programma, registrazione e collegamento Start rimossi; risorse esterne e risultati delle prove conservati.

Il risultato strutturato è in `verification/installer-test.json`. Anche questa prova è stata eseguita sul computer di sviluppo, non su una VM Windows pulita. Il setup è in italiano, non richiede amministratore e non scarica il modello durante l'installazione. Il download viene avviato dall'app al primo utilizzo. Installer non firmato digitalmente; checksum in `dist/CHECKSUMS.sha256`.
