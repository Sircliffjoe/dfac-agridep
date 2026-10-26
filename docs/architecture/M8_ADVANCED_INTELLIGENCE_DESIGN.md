# DFAC AgriDEP - Milestone M8: Advanced Intelligence Extension Architecture
## Phase 4 Architectural Blueprint & Integration Specifications (Design Document)

---

## Executive Summary

This document specifies the technical design, data schemas, API integration contracts, and pipeline architecture for **Phase 4 Advanced Intelligence Extensions** in the **DFAC AgriDEP** platform.

The core platform (Milestones M0 through M7) establishes foundational digital registries, biometric and water quality tracking, field inspection geofencing, offline mobile synchronization, SMS/USSD telecommunication channels, agro-input delivery gating, and automated donor M&E reporting. Milestone M8 defines how advanced AI, earth observation, meteorological, and algorithmic capabilities plug into this existing infrastructure without destabilizing core business operations.

```
                      +-------------------------------------------------------------+
                      |                 DFAC AgriDEP Core Platform                  |
                      |  (Registry, Production, FieldOps, Finance, Market, Alerts)  |
                      +------------------------------+------------------------------+
                                                     |
             +-----------------------+---------------+-----------------------+
             |                       |                                       |
             v                       v                                       v
+------------------------+ +--------------------+ +--------------------+ +------------------------+
| 1. Predictive ML Yield | | 2. Earth           | | 3. Meteorological  | | 4. Multi-Buyer         |
|    Inference Engine    | |    Observation     | |    Weather Feed    | |    Cooperative Pool    |
| (Catfish FCR & Cassava)| | (Sentinel-2 & SAR) | | (ECMWF / Meteo API)| |    Matching Engine     |
+------------------------+ +--------------------+ +--------------------+ +------------------------+
```

---

## 1. Predictive Machine Learning Yield Models Architecture

### 1.1 Problem Statement & Objectives
Smallholder aquaculture in the Niger Delta suffers from unpredictable growth rates due to variable water quality (DO, pH, ammonia), fluctuating feed conversion efficiency, and unrecorded mortality. Similarly, smallholder cassava production exhibits substantial yield variance across soil types and harvest timing.

The Predictive Yield Engine achieves two objectives:
1. **Dynamic Harvest Quantity & Date Forecasting**: Predicts final biomass (kg) and earliest commercially viable harvest date ($\pm 5$ days) to enable forward contracting with off-takers 30–60 days in advance.
2. **Early-Warning Anomaly Detection**: Compares weekly field observations against species-specific growth trajectories. If observed growth falls $> 15\%$ below the expected pace, an automated `RiskFlag` is raised for field officer inspection.

### 1.2 Mathematical & Algorithmic Formulation

#### Aquaculture (African Catfish - *Clarias gariepinus*)
Growth dynamics follow an empirical modified von Bertalanffy growth function (VBGF) coupled with temperature-dependent metabolic scaling:

$$W(t) = W_\infty \left(1 - e^{-K(T) \cdot (t - t_0)}\right)^b$$

Where:
- $W(t)$: Projected average fish weight at day $t$ (grams).
- $W_\infty$: Asymptotic maximum table weight (typically 1,800g – 2,200g).
- $K(T) = K_{ref} \cdot Q_{10}^{\frac{T - T_{ref}}{10}}$: Metabolic growth coefficient scaled by mean pond water temperature $T$ (°C).
- $b$: Allometric scaling exponent ($2.95 \le b \le 3.15$).

Projected pond biomass $B(t)$ incorporates cumulative mortality hazard $S(t)$:

$$B(t) = N_0 \cdot S(t) \cdot W(t)$$

$$S(t) = \exp\left(-\int_0^t \lambda(u, \mathbf{x}_u) \, du\right)$$

Where $\lambda(u, \mathbf{x}_u)$ is a Cox proportional hazards model conditioned on covariate vector $\mathbf{x}_u$ (dissolved oxygen $< 4.0\text{ ppm}$, pH fluctuations, feeding rate).

#### Arable Crops (Cassava - *Manihot esculenta*)
Yield is modeled using Light Use Efficiency (LUE) driven by satellite vegetation indices:

$$Y = \epsilon \cdot \sum_{t=t_{emerge}}^{t_{harvest}} \left( \text{PAR}_t \cdot f\text{APAR}_t \cdot f_T(T_t) \cdot f_W(W_t) \right) \cdot \text{HI}$$

Where:
- $\text{PAR}_t$: Photosynthetically active radiation from ECMWF solar flux.
- $f\text{APAR}_t \approx 1.2 \cdot \text{NDVI}_t - 0.18$: Fractional absorbed PAR derived from Sentinel-2.
- $f_T, f_W$: Temperature and water stress attenuation scalars ($0.0 \le f \le 1.0$).
- $\text{HI}$: Harvest index for root storage ($0.45 \le \text{HI} \le 0.58$).

### 1.3 Machine Learning Pipeline Architecture

```
+--------------------+      +--------------------+      +--------------------+
|  Feature Store     |      |  Inference Service |      |  AgriDEP Consumer  |
|  (PostgreSQL/Redis)| ---> |  (ONNX / Triton)   | ---> |  (Django Signal /  |
| - Biometrics Log   |      | - LightGBM Regr.   |      |   Celery Task)     |
| - Water Chem (pH)  |      | - VBGF Calibration |      | - Update Batch Vol |
| - Weather Covariates|     | - Anomaly Scorer   |      | - Raise RiskFlag   |
+--------------------+      +--------------------+      +--------------------+
```

#### Pipeline Components
1. **Feature Store (`YieldFeatureStore`)**:
   - Ingests daily biometric observations from `ProductionLog` (sampling weight, feed consumed, mortality, DO, pH, water temperature).
   - Enriches entries with 14-day rolling averages of precipitation and ambient temperature from the weather service.
   - Computes rolling Feed Conversion Ratio: $\text{FCR}_{14} = \frac{\Delta \text{Feed (kg)}}{\Delta \text{Biomass (kg)}}$.
2. **Model Training & Versioning**:
   - Framework: LightGBM for tabular tabular feature regression; Scikit-learn Bayesian Ridge for parameter fitting ($W_\infty, K$).
   - Registry: Models packaged in Open Neural Network Exchange (`ONNX`) format and versioned via MLflow (`s3://dfac-models/yield/clarias_v2.onnx`).
3. **Execution Modes**:
   - **Event-Driven**: Triggered via Django post-save signal when an extension officer or farmer submits a `ProductionLog`.
   - **Scheduled Batch**: Celery beat task running weekly at `02:00 UTC` projecting 30-day harvest windows across all active cycles.

### 1.4 Database Schema Blueprint (Phase 4)

```python
class YieldModelType(models.TextChoices):
    CATFISH_VBGF_LGBM = 'CATFISH_VBGF_LGBM', 'Aquaculture Clarias VBGF + LightGBM'
    CASSAVA_LUE_SENTINEL = 'CASSAVA_LUE_SENTINEL', 'Cassava Sentinel-2 LUE Canopy Model'
    POULTRY_BROILER_CURVE = 'POULTRY_BROILER_CURVE', 'Poultry Broiler Gompertz Curve'


class YieldPredictionModel(TimeStampedUUIDModel):
    """Registry of trained predictive yield models."""
    model_name = models.CharField(max_length=128)
    version = models.CharField(max_length=32)
    model_type = models.CharField(max_length=32, choices=YieldModelType.choices)
    enterprise_type = models.ForeignKey('registry.EnterpriseType', on_delete=models.CASCADE)
    artifact_uri = models.CharField(max_length=255, help_text="S3 / GCS model artifact path")
    metrics = models.JSONField(default=dict, help_text="Validation metrics (RMSE, MAPE, R2)")
    is_active = models.BooleanField(default=True)


class YieldPredictionRun(TimeStampedUUIDModel):
    """Inference execution record for a production cycle."""
    cycle = models.ForeignKey('production.ProductionCycle', on_delete=models.CASCADE, related_name='yield_predictions')
    model = models.ForeignKey(YieldPredictionModel, on_delete=models.PROTECT)
    prediction_date = models.DateField(default=timezone.now)
    
    projected_harvest_date = models.DateField()
    projected_volume_kg = models.DecimalField(max_digits=12, decimal_places=2)
    confidence_interval_low_kg = models.DecimalField(max_digits=12, decimal_places=2)
    confidence_interval_high_kg = models.DecimalField(max_digits=12, decimal_places=2)
    
    projected_average_weight_g = models.DecimalField(max_digits=8, decimal_places=2)
    projected_fcr = models.DecimalField(max_digits=4, decimal_places=2)
    projected_survival_rate_pct = models.DecimalField(max_digits=5, decimal_places=2)
    
    anomaly_detected = models.BooleanField(default=False)
    anomaly_score = models.FloatField(default=0.0)
    anomaly_reason = models.TextField(blank=True)
```

---

## 2. Earth Observation & Satellite Remote Sensing Architecture

### 2.1 Satellite Constellations & Sensors

AgriDEP integrates with the **European Space Agency (ESA) Copernicus Data Space Ecosystem** via REST / STAC APIs:

| Sensor | Constellation | Spatial Resolution | Revisit Period | Primary Agricultural Use Case |
| :--- | :--- | :--- | :--- | :--- |
| **MSI (Multispectral Instrument)** | Sentinel-2A / 2B | 10m (B2, B3, B4, B8) | 5 days | Crop canopy vigor (NDVI, NDRE), crop growth tracking, vegetation stress |
| **SAR (C-band Synthetic Aperture Radar)** | Sentinel-1A / 1C | 10m (IW mode) | 6–12 days | All-weather pond surface water mapping, coastal flood extent, cloud penetration |

### 2.2 Vegetation & Moisture Indices

1. **Normalized Difference Vegetation Index (NDVI)**:
   $$\text{NDVI} = \frac{\text{B08 (NIR)} - \text{B04 (Red)}}{\text{B08 (NIR)} + \text{B04 (Red)}}$$
   Monitors canopy emergence and leaf area index in cassava and maize farms.
2. **Normalized Difference Water Index (NDWI)**:
   $$\text{NDWI} = \frac{\text{B03 (Green)} - \text{B08 (NIR)}}{\text{B03 (Green)} + \text{B08 (NIR)}}$$
   Detects earthen pond water boundaries; identifies dried-up or drained fish ponds.
3. **Radar Water Index (SAR Backscatter Ratio)**:
   $$\gamma^0 = \frac{\sigma^0_{VH}}{\sigma^0_{VV}}$$
   Detects open water surface specular reflection even during torrential Niger Delta rainy season cloud cover (June–October).

### 2.3 Imagery Processing Pipeline

```
+-------------------+      +--------------------+      +--------------------+
| Copernicus STAC   |      | Cloud Masking &    |      | Zonal Statistics   |
| Sentinel-2 API    | ---> | Harmonization      | ---> | & Database Sync    |
| - Spatial BBox    |      | - SCL Scene Class  |      | - Intersect Polygon|
| - Cloud Cov < 30% |      | - Resample to 10m  |      | - Store TimeSeries |
+-------------------+      +--------------------+      +--------------------+
```

#### Step-by-Step Dataflow:
1. **Target Area Polling**:
   - The satellite pipeline queries `Farm.objects.filter(is_active=True)` for GPS boundary polygons (`PointField` or `PolygonField`).
   - Generates unified bounding box (BBox) covering Delta (Warri/Ughelli), Bayelsa (Yenagoa), and Rivers (Port Harcourt).
2. **Cloud Masking**:
   - Evaluates Sentinel-2 Scene Classification Layer (SCL). Pixels marked as Cloud High Probability (Class 9), Cloud Medium (Class 8), or Cirrus (Class 10) are masked out.
3. **Zonal Mean Extraction**:
   - Intersects satellite raster tiles with individual smallholder farm polygons via `Rasterio` and `GeoPandas`.
   - Computes mean, median, standard deviation, and pixel count for NDVI, EVI, and NDWI.
4. **Platform Event Dispatch**:
   - If pond surface water index drops below threshold during an active cycle (indicating pond breach or drainage), dispatches an urgent `VisitAssignment` to the field officer.

### 2.4 Database Schema Blueprint (Phase 4)

```python
class SatellitePlatform(models.TextChoices):
    SENTINEL_2_MSI = 'SENTINEL_2_MSI', 'Copernicus Sentinel-2 Optical (10m)'
    SENTINEL_1_SAR = 'SENTINEL_1_SAR', 'Copernicus Sentinel-1 SAR C-Band (10m)'
    PLANET_SCOPE = 'PLANET_SCOPE', 'PlanetScope High-Res Commercial (3m)'


class SatelliteObservation(TimeStampedUUIDModel):
    """Remote sensing zonal observation extracted over a farm boundary."""
    farm = models.ForeignKey('registry.Farm', on_delete=models.CASCADE, related_name='satellite_observations')
    platform = models.CharField(max_length=32, choices=SatellitePlatform.choices)
    scene_id = models.CharField(max_length=128, db_index=True)
    acquisition_datetime = models.DateTimeField()
    cloud_coverage_pct = models.FloatField()
    
    # Vegetation & Water Spectral Indices
    mean_ndvi = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    mean_ndwi = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    mean_ndre = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    mean_evi = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    
    # Water Extent Verification (Aquaculture)
    water_surface_area_sqm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    water_detected = models.BooleanField(default=True)
    
    raw_indices_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-acquisition_datetime']
        unique_together = ('farm', 'scene_id')
```

---

## 3. Meteorological Weather Feeds Architecture

### 3.1 Data Provider & Weather Variables

AgriDEP specifies integration with **ECMWF Integrated Forecasting System (IFS)** models accessed through the Open-Meteo High-Resolution Ensemble API (no proprietary API key required for non-commercial developmental tier, upgradeable to commercial ECMWF HRES 9km feed).

```
                      +-----------------------------+
                      | Open-Meteo / ECMWF Weather  |
                      | 9km High-Resolution API     |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      | WeatherIngestionService     |
                      | (Hourly Ingestion / Cache)  |
                      +--------------+--------------+
                                     |
             +-----------------------+-----------------------+
             |                                               |
             v                                               v
+------------------------+                      +------------------------+
| Daily Agro-Advisory    |                      | Extreme Weather        |
| Rules (AlertService)   |                      | Early Warning Engine   |
| - Low DO Warning       |                      | - Flash Flood Influx   |
| - Heat Stress Alert    |                      | - Torrential Washout   |
+------------------------+                      +------------------------+
```

#### Monitored Meteorological Metrics:
- **Precipitation**: Hourly sum ($\text{mm}$) and 72-hour cumulative accumulation.
- **Surface Ambient Temperature**: Daily $T_{min}$, $T_{max}$, and mean ($^\circ\text{C}$).
- **Relative Humidity**: Mean percentage ($2\text{m}$).
- **Solar Radiation Flux**: Surface shortwave downward irradiance ($\text{W/m}^2$).
- **Wind Speed & Direction**: Maximum gust ($\text{km/h}$ at $10\text{m}$).

### 3.2 Impact on Aquaculture & Agronomic Decisions

1. **Torrential Rain Dilution & Acidity Spike**:
   - Heavy rainfall events ($> 50\text{mm}$ in 24 hours) in Delta/Bayelsa wash acidic topsoils into earthen ponds, causing rapid drops in water pH ($\Delta \text{pH} > 1.5$) and risking fish mortality.
   - *System Action*: Automated SMS advisory dispatched to farmers: *"DFAC Weather Alert: Heavy rain forecast in Warri South. Apply agricultural lime to buffer pond pH and avoid overfeeding."*
2. **Extreme Heat & Hypoxia (Low Dissolved Oxygen)**:
   - Prolonged ambient temperatures $> 34^\circ\text{C}$ coupled with low wind speed sharply reduce dissolved oxygen saturation in standing pond water.
   - *System Action*: Automated alert notifying farmers to aerate ponds or turn on backup submersible pumps during mid-afternoon hours.
3. **Flash Flood Risk Gating**:
   - Predicts riverine overflow for farms located within coastal river basins (Nun River, Forcados River, Escravos).

### 3.3 Database Schema Blueprint (Phase 4)

```python
class WeatherForecastDaily(TimeStampedUUIDModel):
    """Daily micro-climate forecast synced to farm clusters."""
    lga = models.CharField(max_length=64, db_index=True)
    state = models.CharField(max_length=64, default="Delta")
    forecast_date = models.DateField(db_index=True)
    
    temp_max_c = models.DecimalField(max_digits=4, decimal_places=1)
    temp_min_c = models.DecimalField(max_digits=4, decimal_places=1)
    precipitation_sum_mm = models.DecimalField(max_digits=6, decimal_places=2)
    precipitation_probability_pct = models.PositiveSmallIntegerField(default=0)
    max_wind_speed_kmh = models.DecimalField(max_digits=5, decimal_places=2)
    solar_radiation_mj_m2 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    
    flood_risk_level = models.CharField(
        max_length=16,
        choices=[('LOW', 'Low'), ('MODERATE', 'Moderate'), ('HIGH', 'High'), ('SEVERE', 'Severe')],
        default='LOW'
    )
    advisory_generated = models.TextField(blank=True)

    class Meta:
        ordering = ['lga', 'forecast_date']
        unique_together = ('lga', 'state', 'forecast_date')
```

---

## 4. Multi-Buyer Cooperative Pool Matching Architecture

### 4.1 Transition from 1:1 Greedy to N:M Optimal Pooling

In Phase 2 (Milestone M3), the matching algorithm executed **1:N greedy allocation**: an individual buyer demand matched available individual batches within radius order.

In Phase 4, the **Multi-Buyer Cooperative Pool Matching Engine** solves the fragmented smallholder aggregation dilemma:
- **Challenge**: An institutional processor (e.g. Grand Cereals Asaba, Premium Aquaculture Port Harcourt) requires **10 tonnes** of catfish delivered in a single 2-day intake window. Individual smallholders produce between **300kg and 1,500kg** each. Single smallholders cannot fulfill institutional tenders, while buyers refuse to negotiate with 20 individual farmers.
- **Solution**: The cooperative pooling engine groups multiple smallholders within a geographic cluster into an aggregated **Cooperative Produce Pool**, assigns a consolidated waybill, and coordinates clustered off-take transport.

### 4.2 Optimization Formulation (Mixed-Integer Linear Program - MILP)

Let:
- $I = \{1, \dots, n\}$ be the set of available smallholder produce batches.
- $J = \{1, \dots, m\}$ be the set of active commercial buyer demands.
- $x_{ij} \ge 0$ be the volume (kg) allocated from batch $i$ to buyer $j$.
- $y_i \in \{0, 1\}$ indicate whether batch $i$ is included in the consolidation route.

$$\text{Maximize } Z = \sum_{j \in J} \sum_{i \in I} \left( P_j \cdot x_{ij} \right) - \sum_{j \in J} \sum_{i \in I} \left( c_{\text{transport}} \cdot d(i, j) \cdot x_{ij} \right) - \sum_{k \in \text{Clusters}} C_{\text{cluster\_stop}} \cdot y_k$$

**Subject to Constraints:**
1. **Supply Capacity**: $\sum_{j \in J} x_{ij} \le V_i \quad \forall i \in I$ (cannot allocate more than batch volume).
2. **Buyer Demand Fulfillment**: $\sum_{i \in I} x_{ij} \le D_j \quad \forall j \in J$ (cannot exceed requested buyer demand).
3. **Minimum Truckload Threshold**: $\sum_{i \in C_k} x_{ij} \ge V_{\min\_\text{truckload}}$ for each active cluster $C_k$ (e.g. min 3,000kg to dispatch a refrigerated truck).
4. **Temporal Window Overlap**:
   $$[\text{HarvestStart}_i, \text{HarvestEnd}_i] \cap [\text{DeliveryStart}_j, \text{DeliveryEnd}_j] \neq \emptyset$$
5. **Quality Grade Feasibility**: $\text{Grade}_i \ge \text{MinGrade}_j$.

### 4.3 Cluster Routing & Aggregation Hub Workflow

```
+---------------------------------------------------------------------------------+
|                       Cooperative Pool Formation Flow                           |
+---------------------------------------------------------------------------------+
| 1. Algorithm scans ProduceBatch pool for common harvest windows (+/- 4 days).    |
| 2. K-Means spatial clustering groups farms into 15km aggregation radiuses.       |
| 3. Designated Collection Hub identified (e.g. Warri Central Depot).             |
| 4. System reserves buyer contract & locks pool.                                 |
| 5. Master Waybill generated; individual smallholders receive SMS confirmations. |
| 6. Offtake payment delivered into Escrow; settlement distributed proportionally.|
+---------------------------------------------------------------------------------+
```

### 4.4 Database Schema Blueprint (Phase 4)

```python
class PoolStatus(models.TextChoices):
    FORMING = 'FORMING', 'Forming / Gathering Farmer Commitments'
    LOCKED = 'LOCKED', 'Locked / Assigned to Buyer Contract'
    COLLECTING = 'COLLECTING', 'Truck Dispatched for Collection'
    DELIVERED = 'DELIVERED', 'Delivered to Buyer Depot'
    SETTLED = 'SETTLED', 'Escrow Funds Distributed to Farmers'
    CANCELLED = 'CANCELLED', 'Cancelled'


class CooperativeProducePool(TimeStampedUUIDModel):
    """Aggregated multi-farmer produce collection pool."""
    pool_code = models.CharField(max_length=32, unique=True, db_index=True)
    enterprise_type = models.ForeignKey('registry.EnterpriseType', on_delete=models.CASCADE)
    collection_hub_name = models.CharField(max_length=128)
    collection_hub_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    collection_hub_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    
    target_buyer_demand = models.ForeignKey('market.BuyerDemand', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=32, choices=PoolStatus.choices, default=PoolStatus.FORMING)
    
    total_committed_volume_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_delivered_volume_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    agreed_price_per_kg_naira = models.DecimalField(max_digits=10, decimal_places=2)
    total_pool_value_naira = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    scheduled_collection_date = models.DateField()
    master_waybill_number = models.CharField(max_length=64, blank=True)


class PoolMemberAllocation(TimeStampedUUIDModel):
    """Individual smallholder batch contribution to a cooperative pool."""
    pool = models.ForeignKey(CooperativeProducePool, on_delete=models.CASCADE, related_name='members')
    produce_batch = models.ForeignKey('production.ProduceBatch', on_delete=models.CASCADE)
    farmer = models.ForeignKey('registry.Farmer', on_delete=models.CASCADE)
    
    committed_volume_kg = models.DecimalField(max_digits=10, decimal_places=2)
    verified_delivered_volume_kg = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    payout_amount_naira = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_confirmed_by_farmer = models.BooleanField(default=False)
```

---

## 5. Software Interfaces & Abstract Base Classes

To ensure modularity and clean separation of concerns, Phase 4 services adhere to explicit abstract base classes (`ABCs`).

### 5.1 Abstract Yield Predictor Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from datetime import date
from decimal import Decimal

class BaseYieldPredictor(ABC):
    """Abstract interface for species-specific yield prediction algorithms."""

    @abstractmethod
    def predict_harvest(self, cycle_id: str, as_of_date: date) -> Dict[str, Any]:
        """
        Executes forward yield prediction for an active production cycle.
        Returns dict containing:
        - projected_harvest_date: date
        - projected_volume_kg: Decimal
        - confidence_interval: Tuple[Decimal, Decimal]
        - metrics: Dict[str, float] (FCR, survival rate)
        """
        pass

    @abstractmethod
    def detect_growth_anomalies(self, cycle_id: str) -> Dict[str, Any]:
        """
        Evaluates recent biometric trajectory against expected breed curves.
        Returns dict containing:
        - is_anomaly: bool
        - deviation_pct: float
        - severity: str ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
        - recommended_action: str
        """
        pass
```

### 5.2 Abstract Earth Observation Provider Interface

```python
class BaseSatelliteProvider(ABC):
    """Abstract interface for satellite data ingestion providers."""

    @abstractmethod
    def fetch_scene_metadata(self, bbox: List[float], start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Queries satellite catalog STAC API for cloud-masked scenes."""
        pass

    @abstractmethod
    def extract_farm_zonal_indices(self, farm_id: str, scene_id: str) -> Dict[str, float]:
        """
        Clips multispectral or radar raster over farm polygon.
        Returns dict of mean vegetation and water indices:
        {'ndvi': float, 'ndwi': float, 'evi': float, 'water_extent_sqm': float}
        """
        pass
```

### 5.3 Abstract Weather Service Interface

```python
class BaseWeatherProvider(ABC):
    """Abstract interface for high-resolution weather forecast providers."""

    @abstractmethod
    def get_daily_forecast(self, latitude: float, longitude: float, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """Fetches daily forecast variables for coordinates."""
        pass

    @abstractmethod
    def evaluate_weather_risks(self, farm_id: str, forecast: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluates precipitation/heat risk thresholds and returns active advisories."""
        pass
```

---

## 6. Implementation Phasing & Integration Roadmap

```
+---------------------------------------------------------------------------------+
|                       Phase 4 Implementation Schedule                           |
+---------------------------------------------------------------------------------+
| Phase 4.1: Meteorological Integration & Automated SMS Advisories                |
|            - Ingest Open-Meteo weather feeds for Delta/Bayelsa/Rivers.          |
|            - Wire into alerts.services.send_transactional_sms for rain warnings.|
+---------------------------------------------------------------------------------+
| Phase 4.2: Earth Observation (Sentinel-2 & SAR Ingestion)                       |
|            - Connect ESA Copernicus Data Space STAC client.                     |
|            - Setup daily zonal extraction Celery pipeline for registered farms. |
+---------------------------------------------------------------------------------+
| Phase 4.3: Machine Learning Predictive Yield Models                             |
|            - Train baseline VBGF + LightGBM models on historical cycle data.    |
|            - Expose automated harvest date forecasts on DFAC Cockpit.           |
+---------------------------------------------------------------------------------+
| Phase 4.4: Multi-Buyer Cooperative Pool Matching Engine                         |
|            - Deploy MILP cluster pooling algorithm (PuLP / SciPy Optimize).     |
|            - Enable institutional 10-tonne cooperative offtake contracts.       |
+---------------------------------------------------------------------------------+
```

---

## 7. Architectural Compliance Verification

This design satisfies all platform architectural principles:
- **Zero Hard-Coded Constants**: All model thresholds (e.g. anomaly deviation $\ge 15\%$, heavy rainfall limit $\ge 50\text{mm}$, truckload threshold $\ge 3,000\text{kg}$) are read from `SystemParameter.get(...)`.
- **NDPA 2023 Compliance**: Geospatial and remote sensing data masking prevents disclosure of smallholder personally identifiable information (PII) to unauthorized third parties.
- **Offline Compatibility**: All AI predictions and weather forecasts are cached locally within the Flutter Drift mobile database during synchronization intervals.
- **Fail-Safe Operation**: If external satellite or weather APIs experience downtime, the core AgriDEP platform falls back gracefully to standard rule-based heuristics without blocking field operations.
