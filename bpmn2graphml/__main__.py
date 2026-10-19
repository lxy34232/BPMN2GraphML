"""python -m bpmn2graphml：无参数时启动图形界面，有参数时作为命令行使用。"""
import sys

if len(sys.argv) > 1:
    from .cli import main
    sys.exit(main())
else:
    from .gui import run
    run()
