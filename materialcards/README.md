# materialcards/

Material- und Prozessparameter-Karten. Regel P4: nur eigene Messdaten mit dokumentierter Unsicherheit; Platzhalter tragen provisional=true und werden in jedem Bericht ausgewiesen.

- process_window.provisional.json — Prozessfenster (E1-Stufe-2 + Slicer), Zahlen aus S1/S1b/S4. Enthält u. a. die S4-Druckbarkeitsregeln in Strangbreiten (`min_web_width_strand_widths`, `min_inner_radius_strand_widths`, `min_convex_angle_deg`) und die für E1 angenommene Schalenzahl `default_shells`. Die Wanddicken-Untergrenze wird aus Strangbreite × Schalenlogik abgeleitet, solange keine expliziten `wall_thickness_min/max_mm` vorliegen (diese hätten Vorrang).
