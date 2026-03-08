# GraphPad Prism — Comprehensive Feature Inventory

**Version analyzed**: Prism 11.0.0 (released February 17, 2026)
**Platforms**: Windows, macOS
**Company**: GraphPad Software (part of Dotmatics, Insightful Science portfolio)

---

## 1. DATA ENTRY & MANAGEMENT

### Eight Data Table Formats
1. **XY Tables** — every point defined by X and Y values; used with linear/nonlinear regression
2. **Column Tables** — single grouping variable (e.g., control vs. treated groups)
3. **Grouped Tables** — two grouping variables; rows = one variable, columns = another
4. **Contingency Tables** — count data; tabulates number of subjects per group
5. **Survival Tables** — Kaplan-Meier format; elapsed time in X, outcomes in Y columns
6. **Parts of Whole Tables** — fractions of total (pie charts)
7. **Multiple Variables Tables** — spreadsheet-like; each row = observation, each column = variable; supports continuous, categorical, and label/text variables; Excel-style formulas
8. **Nested Tables** — hierarchical/nested replication with two levels (e.g., classrooms nested within teaching methods)

### Data Capacity
- Up to 2,048 columns per table (512 sub-columns each)
- Over 1 million values per row
- Unlimited concurrent windows (removed 16-window restriction in Prism 10)

### Data Import & Entry
- Manual data entry with floating yellow notes explaining format
- Import from CSV, text files
- Import from FCS Express and OMIQ (flow cytometry integrations)
- Sample/tutorial datasets built in (eight types)
- Can change table format after creation

### Data Transformation & Wrangling
- **Calculated variables** — Excel-style formulas in Multiple Variables tables; auto-update when input changes
- **IF() function** — conditional categorical variable creation
- **Standard functions**: min(), max(), mean()
- **Concatenate function** — combine text variables with custom separators
- **NULL handling** — specify blank values in IF() functions
- **AND/OR syntax** — AND(X>3, X<10) format
- Logarithmic transformation
- Value normalization
- Baseline subtraction
- Row/column/grand total fractionation
- Data transposition
- Ratio calculation
- Data subsetting (by column, row range, conditional rules)
- Data restructuring between table formats
- Automatic categorical variable encoding
- "Is Not Missing" row selection option
- Select All/Deselect All batch selection

### File Format
- New open `.prism` format (Prism 10+) — stores raw data, analysis parameters, results, and graphs in industry-standard, accessible format
- Legacy `.pzfx` and `.pzf` files fully supported (Compatibility Mode)
- FAIR data principles support — enables data reuse and research transparency

---

## 2. STATISTICAL ANALYSIS

### Descriptive Statistics
- Min, max, quartiles, mean, SD, SEM
- Confidence intervals
- Coefficient of variation
- Skewness and kurtosis
- Geometric mean with confidence intervals
- Frequency distributions / histograms (including cumulative)

### Normality Testing
- Shapiro-Wilk test
- D'Agostino-Pearson test
- Anderson-Darling test
- Kolmogorov-Smirnov test
- Lognormality testing
- QQ plots

### Outlier Detection
- Grubbs' method
- ROUT method

### T-Tests & Comparisons
- Paired t-test
- Unpaired t-test
- Reports P values AND confidence intervals
- Nested t-tests
- One-sample t-test or Wilcoxon test
- Multiple simultaneous t-tests with FDR or Bonferroni correction

### Nonparametric Tests
- Mann-Whitney test (with median difference confidence intervals)
- Kolmogorov-Smirnov test
- Wilcoxon test (with median confidence intervals)
- Kruskal-Wallis ANOVA with Dunn's post-test
- Friedman test with Dunn's post-test

### ANOVA (Analysis of Variance)
- **One-way ANOVA** — with Tukey, Newman-Keuls, Dunnett, Bonferroni, or Holm-Sidak post-hoc tests
- **Two-way ANOVA** — with missing values support; simultaneous row and column comparisons; select specific pairwise comparisons
- **Three-way ANOVA**
- **N-way (Multifactor) ANOVA** — any factorial design from a single data structure
- **Repeated measures ANOVA** — one-way, two-way, three-way
- **Brown-Forsythe and Welch ANOVA** — for unequal variances
- **Greenhouse-Geisser correction** — for repeated measures
- **Nested one-way ANOVA**
- **Mixed effects models** — for repeated measures with missing data (automatic switch from RM-ANOVA when data missing)
- Jargon-free question-based model selection
- Multiplicity-adjusted P values
- Effect size reporting (eta-squared, Cohen's d, Hedges' g)

### Contingency Tables
- Fisher's exact test
- Chi-square test
- Relative risk calculation
- Odds ratio calculation
- Effect size: Cramer's V

### Correlation
- Pearson correlation
- Spearman (nonparametric) correlation

### Linear Regression
- Slope and intercept with confidence intervals
- Regression line anchoring to specified points
- Replicate Y or mean Y fitting
- Linearity departure testing (runs test)
- Residual calculation (four methods including QQ plot)
- Multiple regression line comparison
- Standard curve interpolation

### Advanced Regression / GLMs
- **Multiple linear regression** — with categorical variable encoding
- **Multiple logistic regression** — binary outcomes
- **Simple logistic regression**
- **Poisson regression** — count data
- **Generalized Linear Models (GLMs)**
- **Deming regression** (Type II)

### Survival Analysis
- Kaplan-Meier survival curves
- Log-rank test (between groups)
- Gehan-Wilcoxon test
- Trend testing
- **Cox proportional hazards regression** — with covariates (continuous and categorical)
- Estimated survival curve generation
- Automatic "Number at Risk" tables

### ROC & Diagnostic
- ROC curves
- Bland-Altman plots

### Dimensionality Reduction
- **Principal Component Analysis (PCA)** — with multiple component selection methods:
  - Parallel Analysis
  - Kaiser criterion
  - Variance threshold
- Scree plots
- Loading plots
- Biplots
- **Principal Component Regression (PCR)** — PCA + regression combined

### Clustering (Machine Learning)
- **K-means clustering** — K-means++ method; silhouette plots
- **Hierarchical clustering** — dendrograms (standalone or with heatmaps)
- Confidence ellipses
- Convex hulls

### Power Analysis & Sample Size
- Multiple experiment designs supported
- Fully adjustable parameters
- Determine sample size for predicted effect size, OR determine smallest detectable effect size for fixed sample size
- Interactive exploration and graphing of parameter relationships
- Contextual explanations for every option

### Simulation
- XY table simulation
- Column table simulation
- Contingency table simulation
- Monte Carlo analysis
- Random number generation (assign subjects to groups)

### Effect Size Reporting (Prism 11)
- Automatically calculated for ANOVAs, contingency tables, and t-tests
- Eta-squared
- Cramer's V
- Cohen's d
- Hedges' g

### P-Value Options
- "One or None" P-value style — single asterisk if p < alpha, none otherwise
- Standard asterisk notation
- Volcano plots (difference vs. P-value)
- P-value stack analysis with FDR/Bonferroni

---

## 3. NONLINEAR REGRESSION / CURVE FITTING

### Equation Library
- **105 built-in equations** including:
  - Dose-response curves (IC50/EC50)
  - Exponential growth
  - Exponential plateau
  - Gompertz growth
  - Logistic growth
  - Beta distribution
  - Enzyme kinetics (Michaelis-Menten, etc.)
  - Saturation binding
  - Radioligand binding
  - Pharmacokinetic models
  - Growth/decay models

### Custom Equations
- User-defined equations (standard form)
- Differential equations
- Implicit equations
- Dataset-specific equations

### Fitting Methods
- **Global nonlinear regression** — share parameters across datasets
- **Robust nonlinear regression** — resistant to outliers
- Automatic outlier identification and elimination
- Constraint application on parameters
- Differential point weighting methods
- Automatic initial value estimation
- Manual initial value estimation

### Model Comparison
- Extra sum-of-squares F-test
- AICc (corrected Akaike Information Criterion)
- Parameter comparison across datasets

### Diagnostics & Quality
- Confidence bands
- Prediction bands
- Residual normality testing
- Runs test / replicates adequacy test
- Covariance matrix reporting
- Parameter precision (SE and CI)
- Hougaard's skewness reporting

### Interpolation & Calculation
- Interpolation from fitted curves
- Intersection point calculation for two lines/curves
- Curve graphing over specified X range
- Area under curve calculation with confidence intervals
- Function plotting from user equations

### Multiple Variables Support (Prism 11)
- Drag-and-drop variable assignment for regression from Multiple Variables tables
- Classic analyses (t-tests, nonlinear regression, Kaplan-Meier) directly from Multiple Variables tables

---

## 4. GRAPH TYPES & VISUALIZATION

### Core Graph Types
- XY scatter plots
- Line graphs
- Bar charts (vertical, horizontal)
- Grouped bar charts
- Stacked bar charts
- Dot plots
- Box-and-whisker plots
- Violin plots (extended or truncated)
- Bubble plots (X, Y, color, size encoding)
- Pie charts / donut charts (parts of whole)
- Histograms / frequency distributions
- Survival curves (Kaplan-Meier)
- Estimation plots
- Volcano plots (difference vs. P-value)
- QQ plots
- Bland-Altman plots
- ROC curves
- Heatmaps (with optional dendrograms)

### Specialized Plots
- Scree plots (PCA)
- Loading plots (PCA)
- Biplots (PCA)
- Dendrograms (hierarchical clustering)
- Confidence ellipses
- Convex hulls
- Smoothing spline (Akima splines, improved knot control)

### Grouped/Combined Graphs
- Scatter + bars + error bars
- Individual points with mean/median markers
- Multiple pairwise comparison visualization
- Stars on graph (statistical comparison results)

### Graph Customization
- Customizable data point styles, sizes, colors, transparency
- Custom labels and fonts
- Error bar styles
- Axis customization (log scales, negative number formatting)
- TeX equation rendering for annotations
- Pairwise comparison drawing tools
- Automatic bar graph labeling (means, medians, sample sizes)
- Graph Portfolio — dozens of polished example graphs demonstrating features
- Infinite graph canvas (unlimited drawing space)
- Select-to-highlight functionality for data groups
- Color ranges based on source data
- Contextual selection (by size or color)
- Symbol sizing for multivariate representation
- Confidence/prediction bands overlay

### Real-Time Updates
- Graphs update automatically when data or analyses change
- Graph Inspector — interactive side panel for real-time customization

---

## 5. AUTOMATION & REPRODUCIBILITY

### Template / Cloning System
- "Family" concept — data table + linked analyses + linked graphs form a family
- Duplicate/clone a family — preserves all analysis settings, graph formatting; just replace data
- Analyses automatically re-run when new data is entered
- Templates available for consistent formatting across projects
- Project structure preserves complete analysis chain

### Analysis Checklists
- Built-in checklists help interpret results
- Guide users through assumption checking
- Reduce analytical errors
- Step-by-step result interpretation

### Calculated Variables (Prism 11)
- Excel-style formulas in data tables
- Auto-update when input data changes
- Eliminates need for separate transformation sheets

### Performance Optimization
- Optimized recalculation logic
- Faster large dataset handling
- Improved sheet switching speed
- Faster saving, exporting, rendering

### Reproducibility Features
- All analysis parameters stored with data in .prism file
- Complete audit trail of analysis choices
- FAIR data principles compliance
- Open file format for data accessibility

---

## 6. EXPORT & REPORTING

### Export Formats
- PNG (customizable resolution and dimensions)
- TIFF
- EPS
- PDF
- SVG
- EMF (Windows)
- CSV (data export)
- JSON
- .prism file (native)
- Legacy .pzfx format

### Export Settings
- Customizable resolution (DPI)
- Customizable dimensions
- Transparency support
- Color space: RGB or CMYK
- Export default presets (save preferred settings)
- Publication-quality output

### Layouts
- Multi-graph layouts for figures
- Annotation tools
- Drawing tools

---

## 7. COLLABORATION (Prism Cloud)

### Publishing & Sharing
- One-click publish from desktop app to Prism Cloud
- Share with anyone via direct links
- Invite specific users with controlled permissions
- Share with Prism users and non-users alike
- Instant updates visible to collaborators

### Viewing
- Browser-based project viewing (no desktop app required)
- Access data tables, analysis results, graphs, and layouts
- Download individual graphs or full .prism files
- Browser file upload (no desktop app required, Prism 11)

### Discussion & Feedback
- In-browser discussion threads
- Centralized communication on projects
- Email notifications for mentions and shares
- Real-time feedback updates

### Organization
- Shared folders (team storage)
- Private folders (individual storage)
- Personal folders (user workspace)
- Groups — share work with multiple users simultaneously

### Workspace Management
- Role-based access (Prism 11 adds Content Manager role)
- Project version history — view and restore previous versions
- Shared workspace for team subscriptions
- Expanded storage options (Enterprise)

---

## 8. INTEGRATIONS

### Flow Cytometry
- **OMIQ** — FCS data import as Prism files
- **FCS Express** — direct data integration

### Electronic Lab Notebooks
- **LabArchives** — ELN integration

### Enterprise Platform
- **Dotmatics Luma** — multimodal R&D platform
- **Protein Metrics** (forthcoming)

### Enterprise IT
- **SSO**: SAML 2.0 and OIDC support
- **SCIM**: Automatic user provisioning/deprovisioning
- **Identity providers**: Microsoft Entra ID, Okta, JumpCloud, Shibboleth
- **Shared device activations**: Machine-based seats
- **Command Line Interface** (forthcoming)

---

## 9. AI / MACHINE LEARNING FEATURES

### Currently Available
- **K-means clustering** (K-means++ method) — Enterprise plan
- **Hierarchical clustering** with dendrograms — Enterprise plan
- **PCA** (Principal Component Analysis)
- **Principal Component Regression (PCR)**
- **Multiple linear regression** with automatic categorical encoding
- **Multiple logistic regression**
- **Poisson regression**
- **GLMs** (Generalized Linear Models)
- Confidence ellipses and convex hulls visualization

### What Prism Does NOT Have
- No LLM/AI-powered natural language interface
- No AI-driven interpretation of results
- No automated report generation with AI narrative
- No structural biology / protein analysis
- No genomics/proteomics pipelines
- No AI-powered literature search or context
- No connection to biological databases (PubMed, UniProt, PDB, etc.)
- No drug target analysis
- No variant/mutation analysis
- No clinical trial search
- No bias/audit detection for AI model outputs
- No foundation model confidence assessment

---

## 10. EDUCATIONAL & SUPPORT RESOURCES

### Built-In Learning
- "Getting Started in Prism" video series
- "Essential Statistics in Prism" videos
- "Graphing Basics in Prism" videos
- "Statistics Bootcamp" fundamentals
- Tutorial datasets (eight kinds)
- Graph Portfolio — polished example graphs with step-by-step instructions
- Analysis Checklists — guide result interpretation
- Floating yellow notes explaining data formats
- Three comprehensive guides: User Guide, Statistics Guide, Curve Fitting Guide

### QuickCalcs (Free Online Tools)
- **Categorical data**: Fisher's test, Chi-square, McNemar's, Sign test, CI of proportion, NNT
- **Continuous data**: Descriptive statistics, outlier detection, t-test, CI of mean/difference/ratio/SD, multiple comparisons, linear regression
- **Statistical distributions**: Calculate P from t/z/r/F/chi-square (and vice versa); view Binomial/Poisson/Gaussian distributions; correct P for multiple comparisons; Bayes
- **Random numbers**: Assign subjects to groups, simulate data
- **Chemical/Radiochemical**: Molar solutions, moles-grams conversion, radioactivity calculations

---

## 11. PRICING TIERS

| Plan | Price | Key Differentiators |
|------|-------|-------------------|
| Student (Annual) | $142/yr | 2 devices, Cloud workspace |
| Academic (Annual) | $260/yr | Same as student, degree-granting institution |
| Corporate (Annual) | $520/yr | Individual use |
| Monthly | $50/mo | Short-term projects |
| Group Academic (2 seats) | $520/yr | Team management, IT tools |
| Group Corporate (2 seats) | $1,120/yr | Team management, IT tools |
| Enterprise | Custom | SSO, SCIM, ML features, premium support |
| Perpetual (Corporate) | $3,200 one-time | No upgrades, no support |

---

## 12. KEY DIFFERENTIATORS & UNIQUE STRENGTHS

1. **Biomedical focus** — purpose-built for life sciences; dose-response, survival analysis, enzyme kinetics are first-class citizens
2. **No coding required** — entirely GUI-driven; designed for bench scientists, not programmers
3. **Analysis checklists** — built-in guidance for interpreting results and checking assumptions
4. **Linked data-analysis-graph families** — change data and everything downstream updates automatically
5. **105 built-in equations** — largest curated equation library for biomedical curve fitting
6. **Publication-quality output** — graphs are journal-ready without post-processing
7. **Jargon-free model selection** — asks plain-English questions to guide statistical test choice
8. **FAIR data compliance** — open file format, complete reproducibility chain
9. **Flow cytometry integration** — direct pipelines from OMIQ and FCS Express
10. **Trusted brand** — decades of usage in pharma, biotech, and academia; widely cited in publications

## 13. TYPICAL USER WORKFLOW

1. Open Prism, select one of eight data table types from Welcome dialog
2. Enter data manually or import from CSV/integrations
3. Click "Analyze" button; Prism asks jargon-free questions to guide test selection
4. Configure analysis parameters (defaults available for speed)
5. View results on results sheet; use Analysis Checklist to interpret
6. Navigate to auto-generated graph; customize with Graph Inspector
7. Add annotations, statistical stars, pairwise comparisons
8. Export as publication-quality PNG/PDF/EPS/SVG
9. Optionally publish to Prism Cloud for team review
10. Clone the family for next experiment — all settings preserved, just replace data
