# Doc Anon 0.2.0 — qualità PDF e anteprima

## Modifiche

- Selettore di esportazione: Compatta 150 DPI, Standard 300 DPI (predefinita), Alta 600 DPI. Entrambe le copie usano la qualità scelta.
- Compressione immagini senza perdita applicata subito a ciascuna pagina, evitando di conservare immagini RGB non compresse fino al salvataggio. Limite di rendering separato dall'OCR, circa 40 MP per pagina, sufficiente per un A4 intero a 600 DPI. Per pagine più grandi l'interfaccia indica le riduzioni di risoluzione. Limite immagini compresse: 256 MiB per variante.
- Anteprima con ridisegno dal PDF originale della porzione visibile quando si aumenta lo zoom o si scorre; supporto densità del monitor e Ctrl + rotella. Zoom indicato in percentuale.
- Le coordinate delle selezioni restano in punti PDF. Un livello di dettaglio non modifica selezione, rettangoli o approvazione. Il rendering dell'anteprima non si sovrappone ai job di analisi/esportazione.
- Installer 0.2.0 con la stessa identità della versione 0.1.0; modello e cartella delle risorse non cambiano.

## Prove del 4 novembre 2026

La suite comprende **28 test** con Python 3.12 / Windows 11: 25 test del motore PDF e delle risorse, 2 dell'interfaccia e 1 con modello reale e OCR. Copertura aggiunta: dimensioni effettive delle immagini nelle due copie a tutte e tre le risoluzioni, rimozione del testo e dei pixel sensibili anche a 600 DPI, parametri di qualità non validi, dettaglio dell'anteprima confrontato pixel per pixel con un rendering diretto del PDF, allineamento su pagine ruotate e ritagliate, limiti di memoria, trasmissione della qualità dall'interfaccia fino ai PDF esportati, stabilità delle selezioni durante zoom/scorrimento e sospensione del rendering durante i job. Un test su più pagine verifica che le immagini siano già compresse nel documento in memoria prima di aggiungere la pagina successiva, senza attendere il salvataggio finale. Il limite dimensionale viene verificato sui flussi compressi effettivamente inseriti nel PDF.

L'eseguibile compilato ha inoltre superato la prova con modello reale, PDF e scansione sintetici, entrambe le copie a 150/300/600 DPI e dettaglio dell'anteprima. Zero tentativi di connessione. Il risultato è in `self-test-0.2.0.json`; `review-0.2.0.png` e `zoom-0.2.0.png` sono catturati dall'eseguibile.

Per le prove dell'installer viene utilizzata una variante con identità distinta (`-TestBuild` / `-Isolated`) e identico payload, dato che sul computer è installata e aperta la versione 0.1.0. La verifica confronta anche versione, cartella e hash dell'installazione esistente prima e dopo il test. Risultato in `installer-test.json`.

Queste verifiche sono eseguite sul computer di sviluppo; non sostituiscono una prova su una macchina Windows pulita. L'aumento di risoluzione non recupera dettagli già persi nella scansione originale. Installer ed eseguibile non sono firmati digitalmente.
