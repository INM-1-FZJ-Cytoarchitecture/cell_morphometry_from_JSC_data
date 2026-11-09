function feat = extract_morphometric_features(tsv_file, mask_file, meta, varargin)
%EXTRACT_MORPHOMETRIC_FEATURES  One morphometric feature row for one ROI.
%
%   FEAT = EXTRACT_MORPHOMETRIC_FEATURES(TSV_FILE, MASK_FILE, META, ...)
%
%   TSV_FILE : <roi>_CellInstances.tsv(.gz) from cmjsc convert (skimage
%              regionprops of the JSC, raw values)
%   MASK_FILE: <roi>_mask.tif (RegionAnnotation of the ROI, JBA_TA)
%   META     : one-row table from cellseg_labels.tsv (roi_stem, brain_id,
%              section_number, OST_id, OST_label, side, trace, include_row, ...)
%
%   Name-Value:
%     'percentile_trim' [] | [low high]  drop the lowest/highest % of cells by
%                       area before all statistics (Thalamus: [1 1])
%     'pixel_size_mm'   default 0.001 (1 um/px)
%
%   Formulas are those of the Thalamus morphometry (2026-04,
%   F:\large_folder_unsynched\Texturanalyse_Harry_Uylings_conmplete_Thalamus\
%   extract_morphometric_features.m) with two deliberate changes:
%     - cell positions = skimage centroid (x_px, y_px) instead of the initial
%       CPN location_x/y (advice Eric Upschulte),
%     - no thalamus-specific areal mapping; labels come from META.
%   MATLAB regionprops is used ONLY for the geometry of the ROI mask.

p = inputParser;
addParameter(p, 'percentile_trim', [], @(x) isempty(x) || (isnumeric(x) && numel(x)==2));
addParameter(p, 'pixel_size_mm', 0.001, @(x) isnumeric(x) && isscalar(x) && x > 0);
parse(p, varargin{:});
percentile_trim = p.Results.percentile_trim;
pixel_size_mm = p.Results.pixel_size_mm;

% ---- mask geometry (MATLAB regionprops only for the RegionAnnotation) ----
mr = imread(mask_file);
mask = logical(mr(:,:,1));
mask_area_px = sum(mask(:));
mask_area_mm2 = mask_area_px * pixel_size_mm^2;
mask_perim_mm = NaN; mask_compactness = NaN; mask_aspect_ratio = NaN;
try
    bnds = bwboundaries(mask, 'noholes');
    if ~isempty(bnds)
        len_px = 0;
        for b = 1:numel(bnds)
            d = diff(bnds{b}, 1, 1);
            len_px = len_px + sum(sqrt(sum(d.^2, 2)));
        end
        mask_perim_mm = len_px * pixel_size_mm;
        if mask_area_mm2 > 0
            mask_compactness = mask_perim_mm^2 / (4*pi*mask_area_mm2);
        end
    end
    rp = regionprops(mask, 'MajorAxisLength', 'MinorAxisLength');
    if ~isempty(rp)
        mj = max([rp.MajorAxisLength]); mn = max([rp.MinorAxisLength]);
        if mn > 0, mask_aspect_ratio = mj / mn; end
    end
catch
end

% ---- cells -------------------------------------------------------------
T = read_cell_instances(tsv_file);
n_before = height(T);
if ~isempty(percentile_trim) && n_before > 0
    a = T.cell_area_px; a = a(isfinite(a));
    if ~isempty(a)
        q = quantile(a, [percentile_trim(1)/100, 1 - percentile_trim(2)/100]);
        T = T(T.cell_area_px >= q(1) & T.cell_area_px <= q(2), :);
    end
end
n_after = height(T);

px_um = pixel_size_mm * 1000; px_um2 = px_um^2;
area_um2 = colvec(T, 'cell_area_px') * px_um2;
perim_um = colvec(T, 'cell_perimeter') * px_um;
feret_um = colvec(T, 'cell_feret_diameter_max') * px_um;
ecc      = colvec(T, 'cell_eccentricity');
sol      = colvec(T, 'cell_solidity');
int_mean = colvec(T, 'cell_intensity_mean');
int_std  = colvec(T, 'cell_intensity_std');
x_px     = colvec(T, 'x_px');
y_px     = colvec(T, 'y_px');

circ = nan(size(area_um2));
ok = perim_um > 0 & isfinite(area_um2);
circ(ok) = 4*pi*area_um2(ok) ./ (perim_um(ok).^2);

cell_density_per_mm2 = NaN; total_cell_area_fraction = NaN;
if mask_area_mm2 > 0
    cell_density_per_mm2 = n_after / mask_area_mm2;
    total_cell_area_fraction = nansum_(area_um2) / (mask_area_mm2 * 1e6);
end

nn_mean_um = NaN; nn_sd_um = NaN; clark_evans_R = NaN; voronoi_cv = NaN; voronoi_n_used = 0;
ok_loc = isfinite(x_px) & isfinite(y_px);
if sum(ok_loc) >= 2
    P = [x_px(ok_loc), y_px(ok_loc)] * px_um;
    n_loc = size(P, 1);
    [~, d2] = knnsearch(P, P, 'K', 2);
    nn = d2(:, 2);
    nn_mean_um = mean(nn, 'omitnan'); nn_sd_um = std(nn, 'omitnan');
    if mask_area_mm2 > 0 && isfinite(nn_mean_um)
        expected_mm = 0.5 * sqrt(mask_area_mm2 / n_loc);
        if expected_mm > 0, clark_evans_R = (nn_mean_um * 1e-3) / expected_mm; end
    end
    % Voronoi area CV with edge correction (KI-006, since 1.2.0): only cells whose
    % Voronoi polygon lies completely inside the RegionAnnotation (all vertices in
    % the mask; minus-sampling). Border cells, whose polygons are bounded only by
    % the convex hull of the point set, no longer enter. No upper cell limit
    % (was n <= 80000).
    if n_loc >= 4
        try
            DT = delaunayTriangulation(P);
            [V, R] = voronoiDiagram(DT);
            [mh, mw] = size(mask);
            vc = round(V(:,1) / px_um) + 1; vr = round(V(:,2) / px_um) + 1;   % um -> 1-based px (skimage 0-based)
            vin = all(isfinite(V), 2) & vc >= 1 & vc <= mw & vr >= 1 & vr <= mh;
            vmask = false(size(V, 1), 1);
            vmask(vin) = mask(sub2ind([mh mw], vr(vin), vc(vin)));
            areas = nan(numel(R), 1);
            for k = 1:numel(R)
                idx = R{k};
                if numel(idx) < 3 || any(idx == 1) || ~all(vmask(idx)), continue; end
                areas(k) = polyarea(V(idx,1), V(idx,2));
            end
            areas = areas(isfinite(areas) & areas > 0);
            voronoi_n_used = numel(areas);
            if voronoi_n_used >= 5, voronoi_cv = std(areas) / mean(areas); end
        catch
        end
    end
end
log_area = log(area_um2(area_um2 > 0));

s = struct();
for v = {'roi_stem','brain_id','section_number','OST_label','OST_id','side'}
    if ismember(v{1}, meta.Properties.VariableNames), s.(v{1}) = string(meta.(v{1})(1)); else, s.(v{1}) = ""; end
end
s.side_num = double(s.side == "r");
s.trace = double(meta.trace(1));
if ismember('include_row', meta.Properties.VariableNames), s.include_row = double(meta.include_row(1)); else, s.include_row = NaN; end
s.n_before_trim = n_before;
s.n_after_trim = n_after;
s.mask_area_px = mask_area_px;
s.mask_area_mm2 = mask_area_mm2;
s.mask_perim_mm = mask_perim_mm;
s.mask_compactness = mask_compactness;
s.mask_aspect_ratio = mask_aspect_ratio;
s.n_cells = n_after;
s.cell_density_per_mm2 = cell_density_per_mm2;
s.total_cell_area_fraction = total_cell_area_fraction;
s.area_mean_um2 = nanmean_(area_um2);
s.area_sd_um2 = nanstd_(area_um2);
s.area_median_um2 = nanmedian_(area_um2);
s.area_p10_um2 = pct(area_um2, 10);
s.area_p25_um2 = pct(area_um2, 25);
s.area_p75_um2 = pct(area_um2, 75);
s.area_p90_um2 = pct(area_um2, 90);
s.area_skew = safe_skew(area_um2);
s.log_area_mean = nanmean_(log_area);
s.log_area_sd = nanstd_(log_area);
s.circularity_mean = nanmean_(circ);
s.circularity_sd = nanstd_(circ);
s.eccentricity_mean = nanmean_(ecc);
s.eccentricity_sd = nanstd_(ecc);
s.solidity_mean = nanmean_(sol);
s.solidity_sd = nanstd_(sol);
s.feret_max_mean_um = nanmean_(feret_um);
s.intensity_mean_mean = nanmean_(int_mean);
s.intensity_mean_sd = nanstd_(int_mean);
s.intensity_std_mean = nanmean_(int_std);
s.nn_dist_mean_um = nn_mean_um;
s.nn_dist_sd_um = nn_sd_um;
s.clark_evans_R = clark_evans_R;
s.voronoi_area_cv = voronoi_cv;
s.voronoi_n_cells_used = voronoi_n_used;
feat = struct2table(s);
end

function v = colvec(T, name)
if ismember(name, T.Properties.VariableNames), v = double(T.(name)); v = v(:); else, v = nan(height(T), 1); end
end
function m = nanmean_(x), x = x(isfinite(x)); if isempty(x), m = NaN; else, m = mean(x); end, end
function s = nanstd_(x), x = x(isfinite(x)); if numel(x) < 2, s = NaN; else, s = std(x); end, end
function m = nanmedian_(x), x = x(isfinite(x)); if isempty(x), m = NaN; else, m = median(x); end, end
function m = nansum_(x), x = x(isfinite(x)); if isempty(x), m = NaN; else, m = sum(x); end, end
function q = pct(x, p), x = x(isfinite(x)); if isempty(x), q = NaN; else, q = quantile(x, p/100); end, end
function s = safe_skew(x)
x = x(isfinite(x));
if numel(x) < 3, s = NaN; return; end
m = mean(x); sd = std(x);
if sd == 0, s = 0; else, s = mean(((x - m) / sd).^3); end
end
