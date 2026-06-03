TEMPLATE = {
    "name": "专志",
    "description": "部门志/行业志/专志篇目",
    "outline_template": [
        {"title": "序", "level": 0, "required": True},
        {"title": "凡例", "level": 0, "required": True},
        {"title": "概述", "level": 1, "required": True},
        {"title": "大事记", "level": 1, "required": True},
        {
            "title": "机构沿革",
            "level": 1,
            "children": [
                {"title": "机构设置", "level": 2},
                {"title": "历任负责人", "level": 2},
            ],
        },
        {
            "title": "业务发展",
            "level": 1,
            "children": [
                {"title": "发展历程", "level": 2},
                {"title": "主要成就", "level": 2},
                {"title": "业务管理", "level": 2},
            ],
        },
        {
            "title": "队伍建设",
            "level": 1,
            "children": [
                {"title": "人员结构", "level": 2},
                {"title": "教育培训", "level": 2},
            ],
        },
        {"title": "荣誉表彰", "level": 1},
        {"title": "附录", "level": 1, "required": True},
        {"title": "编纂始末", "level": 0, "required": True},
        {"title": "后记", "level": 0, "required": True},
    ],
    "editorial_notes_template": (
        "一、本志如实记述本行业/部门发展历程。\n"
        "二、本志上限自机构成立之日，下限至编纂年份。\n"
        "三、本志采用述、记、志、图、表、录等体裁。\n"
        "四、本志引文均标注来源。"
    ),
}
