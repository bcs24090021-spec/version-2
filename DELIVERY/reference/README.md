# reference

## Data
1. NASA FIRMS (Fire Information for Resource Management System) — the only data source used. https://www.earthdata.nasa.gov/data/tools/firms
   - Country-year archive (Standard Processing): https://firms.modaps.eosdis.nasa.gov/data/country/
   - File index with sizes: https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt
   - Products: MODIS Collection 6.1 (MCD14ML, Aqua/Terra, 1 km), VIIRS 375 m (VNP14IMGTDL, Suomi NPP)
   - FAQ and attribute tables: https://www.earthdata.nasa.gov/data/tools/firms/faq

## Papers
2. Schroeder, W. et al. (2014). The New VIIRS 375 m active fire detection data product. *Remote Sensing of Environment* 143:85–96. https://doi.org/10.1016/j.rse.2013.12.008 — why VIIRS sees more small fires than MODIS.
3. Giglio, L., Schroeder, W., Justice, C.O. (2016). The collection 6 MODIS active fire detection algorithm and fire products. *Remote Sensing of Environment* 178:31–41. https://doi.org/10.1016/j.rse.2016.02.054 — MODIS confidence classes and pixel growth with scan angle.
4. Li, F., Zhang, X., Kondragunta, S. (2020). Biomass burning in Africa: FRP missed by MODIS using the 375 m VIIRS product. *Remote Sensing* 12(10):1561. https://doi.org/10.3390/rs12101561 — pairing rules (time, footprint, duplicates).
5. Fu, Y. et al. (2020). Fire detection and FRP in Northeast Asia: MODIS versus VIIRS. *Remote Sensing* 12(18):2870. https://doi.org/10.3390/rs12182870 — MODIS/VIIRS comparison, confidence filtering.
6. Zheng, Y. et al. (2026). FRP correction and spatiotemporal fusion based on MYD14 and VNP14IMG. *Remote Sensing* 18(10):1650. https://doi.org/10.3390/rs18101650 — MODIS–VIIRS fusion.
7. Breiman, L. (2001). Random Forests. *Machine Learning* 45:5–32. https://doi.org/10.1023/A:1010933404324 — the model.
8. Roberts, D.R. et al. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography* 40:913–929. https://doi.org/10.1111/ecog.02881 — why we test by leaving out whole years.

## Software
9. scikit-learn (RandomForestRegressor), pandas, NumPy, SciPy (cKDTree), pyproj, matplotlib — all open source (BSD/MIT).

## AI use
Analysis code and documentation were developed with AI assistants (Claude, Cursor agents) under human direction; all numbers were recomputed from the FIRMS data.
