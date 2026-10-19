# El DOF sin drama

Página gratis que toma el sumario del Diario Oficial de la Federación (servicio abierto SIDOF de Gobernación), lo ordena por tema y enlaza al texto oficial. Se actualiza sola con GitHub Actions y se publica con GitHub Pages.

## Subirlo (sin terminal)
1. En GitHub: **New repository** → nombre `dof-sin-drama` → **Public** → Create.
2. **Add file → Upload files**: arrastra TODO el contenido de esta carpeta (incluida `.github`, `scripts`, `data`). Si tu navegador no sube carpetas ocultas, crea el archivo `.github/workflows/dof-diario.yml` con **Add file → Create new file** y pega su contenido.
3. **Settings → Pages**: Source = *Deploy from a branch*, Branch = `main`, carpeta `/ (root)`. Guardar.
4. **Settings → Actions → General → Workflow permissions**: *Read and write permissions*. Guardar.
5. Pestaña **Actions → Actualizar DOF → Run workflow** (pon `14` en días atrás para llenar dos semanas). Revisa que termine en verde.
6. Tu página: `https://TU-USUARIO.github.io/dof-sin-drama/`

## Qué revisar la primera semana
- Si el paso 5 falla con error de conexión, SIDOF podría bloquear las IP de GitHub: avísame y buscamos alternativa.
- SIDOF no tiene documentación oficial; si cambia su formato habrá que ajustar `scripts/fetch_dof.py`.
- Confirma a qué hora sale la matutina y ajusta los `cron` (están en UTC; CDMX = UTC-6).

## Reglas del proyecto
Siempre enlazar al texto oficial · “Resumen informativo, no asesoría legal” · lo dudoso se marca “pendiente de confirmar” · sin resúmenes de IA en la etapa 1 (la página ya soporta `resumen: {dice, significa}` por nota para la etapa 2).

Prueba local: `python scripts/fetch_dof.py --dias-atras 3` y `python -m http.server`.
