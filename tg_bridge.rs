use moviebox_tui::providers::models::{ProviderKind, Release};
use moviebox_tui::providers::ReleaseProvider;
use moviebox_tui::service::MovieBoxService;
use serde_json::json;

fn streams_to_json(mut streams: Vec<Release>) -> (Vec<serde_json::Value>, String) {
    let res_id = streams.iter().find_map(|r| r.resource_id.clone()).unwrap_or_default();
    streams.sort_by(|a, b| b.resolution_u64().cmp(&a.resolution_u64()));
    let mut out = Vec::new();
    for r in streams {
        let res = r.resolution_u64();
        let size_mb = r.size_bytes.map(|b| b / 1_048_576);
        for m in r.mirrors {
            if m.resolver_url.is_empty() { continue; }
            out.push(json!({
                "filename": r.filename, "quality": r.quality, "resolution": res,
                "codec": r.codec, "language": r.language, "size_mb": size_mb,
                "mirror": m.label, "url": m.resolver_url, "headers": m.headers
            }));
        }
    }
    out.sort_by_key(|v| if v["url"].as_str().unwrap_or("").contains(".mpd") { 1 } else { 0 });
    (out, res_id)
}

async fn fetch_streams(s: &MovieBoxService, p: ProviderKind, id: &str, se: usize, ep: usize) -> Result<Vec<Release>, String> {
    let res = match p {
        ProviderKind::MovieBox => s.client.episode_streams(id, se, ep).await,
        ProviderKind::FourKHdHub => match s.fourk_client.as_ref() {
            Some(c) => c.episode_streams(id, se, ep).await,
            None => return Err("4KHDHub unavailable".into()),
        },
        ProviderKind::BdixCircleFtp => s.circleftp_client.episode_streams(id, se, ep).await,
        ProviderKind::BdixDhakaFlix => s.dhakaflix_client.episode_streams(id, se, ep).await,
        ProviderKind::Dramachi => ReleaseProvider::episode_streams(&s.dramachi_client, id, se, ep).await,
        ProviderKind::Addons => return Err("Addons streams not supported".into()),
    };
    res.map_err(|e| e.to_string())
}

#[tokio::main]
async fn main() {
    let args: Vec<String> = std::env::args().collect();
    let cmd = args.get(1).map(|s| s.as_str()).unwrap_or("");
    let service = MovieBoxService::new();
    let prov = ProviderKind::parse(args.get(2).map(|s| s.as_str()).unwrap_or("moviebox")).unwrap_or(ProviderKind::MovieBox);

    match cmd {
        "search" => match service.search_typed(prov, &args[3..].join(" "), 1).await {
            Ok(items) => {
                let results: Vec<_> = items.iter().map(|i| json!({
                    "provider": i.id.provider.cache_key(), "title": i.title,
                    "id": i.id.value, "type": format!("{:?}", i.media_type), "year": i.year
                })).collect();
                println!("{}", json!({"results": results}));
            }
            Err(e) => println!("{}", json!({"error": e.to_string()})),
        },
        "trending" => match service.homepage("", 1).await {
            Ok((items, _)) => {
                let results: Vec<_> = items.iter().take(12).map(|i| json!({
                    "provider": i.id.provider.cache_key(), "title": i.title,
                    "id": i.id.value, "type": format!("{:?}", i.media_type), "year": i.year
                })).collect();
                println!("{}", json!({"results": results}));
            }
            Err(e) => println!("{}", json!({"error": e})),
        },
        "details" => {
            let id = args.get(3).map(|s| s.as_str()).unwrap_or("");
            match service.details_typed(prov, id).await {
                Ok(d) => {
                    let seasons: Vec<_> = d.seasons.iter().map(|s| json!({
                        "number": s.number,
                        "episodes": s.episodes.iter().map(|e| json!({"season": e.season, "number": e.number, "title": e.title})).collect::<Vec<_>>()
                    })).collect();
                    let (mut streams, mut res_id) = (Vec::new(), String::new());
                    if seasons.is_empty() {
                        if let Ok(s) = fetch_streams(&service, prov, id, 1, 1).await { (streams, res_id) = streams_to_json(s); }
                        if streams.is_empty() {
                            if let Ok(s) = fetch_streams(&service, prov, id, 0, 0).await { (streams, res_id) = streams_to_json(s); }
                        }
                    }
                    let caps = if seasons.is_empty() {
                        service.get_ext_captions(id, &res_id, &[], 1, 1).await.unwrap_or_default()
                            .into_iter().map(|c| json!({"name": c.name, "url": c.url})).collect::<Vec<_>>()
                    } else { Vec::new() };
                    let dubs: Vec<_> = d.dubs.iter().map(|x| json!({"id": x.subject_id, "language": x.language, "label": x.label})).collect();
                    println!("{}", json!({
                        "title": d.title, "type": format!("{:?}", d.media_type), "year": d.year,
                        "poster": d.poster_url, "rating": d.imdb_rating, "duration": d.duration,
                        "plot": d.description, "dubs": dubs, "seasons": seasons,
                        "streams": streams, "captions": caps
                    }));
                }
                Err(e) => println!("{}", json!({"error": e.to_string()})),
            }
        }
        "streams" => {
            let id = args.get(3).map(|s| s.as_str()).unwrap_or("");
            let se: usize = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(1);
            let ep: usize = args.get(5).and_then(|s| s.parse().ok()).unwrap_or(1);
            match fetch_streams(&service, prov, id, se, ep).await {
                Ok(s) => {
                    let (streams, res_id) = streams_to_json(s);
                    let caps = service.get_ext_captions(id, &res_id, &[], se, ep).await.unwrap_or_default()
                        .into_iter().map(|c| json!({"name": c.name, "url": c.url})).collect::<Vec<_>>();
                    println!("{}", json!({"streams": streams, "captions": caps}));
                }
                Err(e) => println!("{}", json!({"error": e})),
            }
        }
        _ => println!("{}", json!({"error": "Use search|trending|details|streams"})),
    }
}
