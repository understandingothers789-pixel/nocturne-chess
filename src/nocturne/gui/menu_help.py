"""Plain-language help for menu commands, including generated choices."""

HELP = {
    'New game': 'Choose players, colors and time controls for a new game.',
    'New study tab': 'Open a separate study without closing your current game.',
    'Rename study': 'Change the name shown on the current study tab.',
    'Set up position': 'Place pieces and choose the side to move for a custom position.',
    'New Chess960 position': 'Choose a Chess960 starting arrangement.',
    'Open PGN': 'Choose a PGN file containing games to open.',
    'Load FEN / PGN from clipboard': 'Import the position or game currently copied to your clipboard.',
    'Edit / paste PGN': 'Open the PGN editor to paste or edit game notation.',
    'Enter FEN / PGN': 'Enter a position (FEN) or a complete game (PGN).',
    'Save to library': 'Save the current game and study in the local game library.',
    'Save this game as PGN': 'Choose a file name and location for a PGN copy of this game.',
    'Save to Special Positions': 'Save a named PGN copy in your Special Positions folder.',
    'Saved PGNs / game library': 'Browse and open games saved on this device.',
    'Open saved PGN folder': 'Open the folder containing automatically saved PGN files.',
    'Write PGN to clipboard': 'Copy the game, variations and comments as PGN text.',
    'Write FEN to clipboard': 'Copy only the current board position as FEN text.',
    'Show database explorer': 'Display opening moves and results from the selected database.',
    'Enable database statistics': 'Fetch opening statistics for the current position.',
    'Lichess Masters database (Recommended)': 'Use games from master-level over-the-board play as the opening reference.',
    'Lichess players (Amateurs)': 'Use Lichess player games, filtered by the selected rating and time control.',
    'ChessDB · cloud analysis': 'Use ChessDB cloud engine analysis for the current position.',
    'Set up optional GPU runtime': 'Download and configure optional GPU support for Maia inference.',
    'Smart Move · click recommended destinations': 'Play a recommended move by clicking its destination without first selecting a piece.',
    'Show saved continuation arrows': 'Mark continuations already recorded in the current game tree.',
    'Show Maia insights': 'Display human move predictions, rating curves and move assessments.',
    'Show Game Line notes': 'Display comments and annotations in the game line.',
    'Show Maia evaluation bar label': 'Show the numeric label on the Maia outcome rail.',
    'Show Maia evaluation bar': 'Display the rail representing White’s expected game score.',
    'Always show five Stockfish rows': 'Reserve at least five candidate rows, even before their analysis arrives.',
    'Detailed analysis statistics': 'Display extra search statistics alongside engine analysis.',
    'Show selective depth (seldepth)': 'Show the deepest branch searched, alongside the normal search depth.',
    'Wheel navigates game moves': 'Use the mouse wheel over the game moves area to move backward or forward through the game.',
    'Wheel previews analysis moves': 'Use the mouse wheel over a variation to step through its continuation.',
    'Save analysis snapshots at node milestones': 'Keep engine results at configured node milestones for later comparison.',
    'Compare saved analysis snapshots': 'Compare engine results previously captured at different search sizes.',
    'Show raw PGN data': 'Display the text representation of the current game in a separate tab.',
    'Quit': 'Close Nocturne.',
    'Root': 'Go to the starting position of this game.',
    'End': 'Go to the last move of the current line.',
    'Backward': 'Go back one move.',
    'Forward': 'Go forward one move along the current line.',
    'Return to main line': 'Return from a variation to the main line at this move number.',
    'Previous variation': 'Switch to the previous sibling variation.',
    'Next variation': 'Switch to the next sibling variation.',
    'Promote variation to main line': 'Make the current variation the main continuation.',
    'Delete current line': 'Remove the current variation from the game tree.',
    'Edit comment / annotations': 'Add a comment or a chess annotation symbol to this position.',
    'Bookmark this position': 'Give this position a name so you can return to it quickly.',
    'Go': 'Start engine analysis of the current position.',
    'Halt': 'Stop the current engine search.',
    'Analyze all legal moves again': 'Remove the targeted-move restriction and search all legal moves.',
    'Analyze entire line': 'Choose a search time and analyze positions along the current line.',
    'Pause / resume game analysis': 'Pause an ongoing line review, or continue where it stopped.',
    'Cancel game analysis': 'Stop reviewing the line; completed results remain available.',
    'Game Review': 'Inspect the game review and its move assessments.',
    'Confirm mistakes with deeper analysis': 'Search suspected mistakes more deeply during game review.',
    'Engine diagnostics': 'Inspect the engine connection and UCI communication.',
    'Flip board': 'Switch between White and Black at the bottom of the board.',
    'Arrange panels': 'Unlock panels so you can drag, dock and resize them.',
    'Reset layout': 'Restore the default panel arrangement.',
    'Classic Nibbler layout': 'Apply the classic board and analysis arrangement.',
    'Analysis on the left': 'Place analysis panels to the left of the board.',
    'Board appearance': 'Choose board colors, piece style and other appearance settings.',
    'Save board image': 'Export an image of the current board.',
    'Command palette': 'Find and run a command by typing its name.',
    'Keyboard shortcuts': 'View and customize command shortcuts.',
    'Choose engine': 'Select the UCI engine used for Stockfish-style analysis.',
    'Choose Syzygy folder': 'Select local Syzygy tablebase files for endgame probing.',
    'Engine profiles and options': 'Manage engine executables and their UCI settings.',
    'Auto-play engines from this position': 'Let the engine play both sides from here. Press F11 again to pause or resume.',
    'Auto-evaluate entire line': 'Evaluate each position in the current line using the configured node limit.',
    'Restart selected engine': 'Stop and reconnect the currently selected UCI engine.',
    'Enable local Maia predictions': 'Predict human move choices at the selected rating using the bundled Maia model.',
    'Expand all analysis lines': 'Show the full continuation for every candidate row.',
    'Show Maia rods (moves above 10%)': 'Mark moves Maia predicts more than 10% of players will choose at the selected rating.',
    'Use only one of Maia or Leela': 'Enable one of these models at a time to reduce simultaneous analysis work.',
    'Maia panels on the right': 'Place the Maia insights beside the analysis panel.',
    'Create a Lichess access token': 'Open Lichess in your browser to create an access token.',
    'Clear saved access token': 'Remove the stored Lichess token from this device.',
    'Refresh database results': 'Request fresh opening database results for this position.',
    'Find where this line leaves the database': 'Check the current line for the first move missing from the selected database.',
    'Cancel database coverage scan': 'Stop checking database coverage along the line.',
    'Pause / continue': 'Pause the game and clocks, or continue playing.',
    'Offer / claim draw': 'Offer a draw or claim one when the rules allow it.',
    'Resign': 'End the game by resigning for the current player.',
}


def menu_help(action, menu):
    label = action.text().replace('&', '').replace('…', '').strip()
    explicit = action.toolTip()
    if explicit and explicit != action.text():
        return explicit
    if label in HELP:
        return HELP[label]
    title = menu.title().replace('&', '')
    if action.menu():
        return f'Open {label} settings and choices.'
    if 'node' in title.lower():
        return f'Set the search limit for {title.split(" · ")[0]} to {label}. Nodes count positions searched by the engine.'
    if 'rating groups' in title:
        return f'Filter Lichess games to the {label} rating group.'
    if 'game speed' in title:
        return f'Filter Lichess games by time control: {label}.'
    if label.startswith('Execute candidate '):
        return f'Play the first move of engine candidate {label.rsplit(" ", 1)[-1]}.'
    if action.isCheckable():
        return f'Turn this option on or off: {label}. Checked means enabled.'
    return f'{label}. This command is in {title or "the current menu"}.'
