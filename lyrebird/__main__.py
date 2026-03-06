import sys

if len(sys.argv) > 1 and sys.argv[1] == "sync":
    from lyrebird.cli import sync_main

    sync_main()
else:
    from lyrebird.cli import main

    main()
