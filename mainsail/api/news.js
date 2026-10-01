// Vercel serverless endpoint: GET /api/news
// Fetches the same feeds as the build and is cached at the edge for a day, so the page shows
// fresh headlines daily even if the GitHub workflow has not run. The page falls back to the
// headlines baked into index.html when this endpoint is unavailable (static hosts, previews).
'use strict';
const { fetchNews } = require('../build/lib/newsfetch.js');

module.exports = async (req, res) => {
  try {
    const data = await fetchNews();
    if (!data.items || data.items.length < 6) throw new Error('too few headlines');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'public, s-maxage=86400, stale-while-revalidate=43200');
    res.status(200).end(JSON.stringify(data));
  } catch (e) {
    res.setHeader('Cache-Control', 'no-store');
    res.status(502).json({ error: 'Headlines are temporarily unavailable.' });
  }
};
