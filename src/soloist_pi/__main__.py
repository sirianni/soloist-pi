"""Support ``python -m soloist_pi`` as an alias for the supervisor command."""

from soloist_pi.run import main

raise SystemExit(main())
