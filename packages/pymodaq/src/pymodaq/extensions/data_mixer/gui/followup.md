## Eval
library in eval should be defined from a dict with mandatory keys
np, xr, ...
kernel.shell.push({'np': np, 'xr': xr, '_xr': dict(self._h5_ctx)})


# FallbackEditor
Factorization of methods between _FallbackEditor and PatternCompleter?

# VariableBrowserWidget
Parameter tree could use more columns (one for type, one for shape, ...) with the possibility to decide which columns to display (checkbox the ones you want)

QActions to prepare selected viewers should be possible through right click to test if display is possible/working (can be in the widget / in the data_mixer_gui with icons / or both) pros/cons ?
check @prepare_viewers in load_and_plot.py to see how it is currently implemented. 


# Color palette
Currently badly implemented for darkmode. The palette should be set according the theme. Proposition in @console.py for the FormulaHighlighter which can be discussed and improved. This dicussion can be extented to a larger framework throughout pymodaq.


# Layout
Interest in inheriting CustomApp to have access to parameter manager (settings) and action manager (icons) ?