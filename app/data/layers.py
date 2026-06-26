"""Platform scoring layers (filled after registration / during events)."""

LAYER_NAMES: dict[int, str] = {
    1: "Team Result",
    2: "Head-to-Head Result",
    3: "Individual Contribution",
    4: "Skill / Role Progression",
    5: "Community / Viewer Feedback",
}

LAYER_COLUMNS: dict[int, str] = {
    1: "layer_1_team_result",
    2: "layer_2_head_to_head",
    3: "layer_3_individual",
    4: "layer_4_skill_progression",
    5: "layer_5_community_feedback",
}
