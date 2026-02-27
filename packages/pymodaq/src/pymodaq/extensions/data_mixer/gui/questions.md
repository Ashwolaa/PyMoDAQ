# Questions

# Plotting keywords
Should not be necessarily proposed in the _FallbackEditor


# Parsing
Accessing the coords in a dataset is done by the following syntax:
{detector 01/Mock2D_0}["CH00"]["the_x_axis"] # does not autocomplete the_x_axis
The str pattern completer cannot propose "the_x_axis" as a valid completion but it does it when using a function such as 
b = {detector 01/Mock2D_0}["CH00"].mean("the x axis") # autocomplete the_x_axis

Could the proposition matching what comes before? Currently "the x axis" is proposed in all cases but is not valid for certain dataset 
{detector 00/Mock1D}["CH00"].mean("the x axis")  # autocomplete the_x_axis but the_x_axis is not a valid completion


# Parameter tree
More columns (one for type, one for shape, ...) with the possibility to decide which columns to display (checkbox the one you want)


# InfoPanelWidget
The info on the dataset only refreshes cliking on a computed data, is that intended? 
The computed data are loosing some infos (such as the coordinates when present) compared to the VariableBrowserWidget
Formula used to compute is not displayed. It should be possible to copy / paste it from the info panel to the formula editor


# VariableBrowserWidget
Option with prepare viewer should be possible through right click to test if display is possible/working
check @prepare_viewers in load_and_plot.py to see how it is currently implemented


# Color palette
Currently badly implemented for darkmode. The palette should be set according the theme. Proposition in @console.py for the FormulaHighlighter can be discussed. This dicussion can be extented to a larger framework


# Layout
Interest to use CustomApp to have access to parameter manager (settings) and action manager (icons) ?