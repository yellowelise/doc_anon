import sys

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from doc_anon.selftest import run
        sys.exit(run(sys.argv[2]))
    else:
        from doc_anon.app import main
        main()
