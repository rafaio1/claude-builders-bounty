use crate::config::RegistryConfig;
use anyhow::Result;
use dashmap::DashMap;
use parking_lot::RwLock;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tokio::time::{interval, Duration};

#[derive(Debug, Clone)]
pub struct ServiceEntry {
    pub service_id: String,
    pub service_name: String,
    pub version: String,
    pub endpoints: Vec<String>,
    pub metadata: std::collections::HashMap<String, String>,
    pub registered_at: i64,
    pub ttl: u64,
}

#[derive(Debug, Clone)]
pub enum RegistryEvent {
    Registered(ServiceEntry),
    Deregistered(String),
    Heartbeat(String),
    Expired(String),
}

pub struct ServiceRegistry {
    config: RegistryConfig,
    services: Arc<DashMap<String, ServiceEntry>>,
    events: Arc<RwLock<Vec<RegistryEvent>>>,
    running: Arc<AtomicBool>,
    event_tx: tokio::sync::broadcast::Sender<RegistryEvent>,
}

impl ServiceRegistry {
    pub fn new(config: RegistryConfig) -> Self {
        let (event_tx, _) = tokio::sync::broadcast::channel(1024);
        Self {
            config,
            services: Arc::new(DashMap::new()),
            events: Arc::new(RwLock::new(Vec::new())),
            running: Arc::new(AtomicBool::new(false)),
            event_tx,
        }
    }

    pub async fn initialize(&self) -> Result<()> {
        tracing::info!(
            backend = %self.config.backend,
            endpoints = ?self.config.endpoints,
            replication = %self.config.replication_factor,
            "initializing service registry"
        );

        self.running.store(true, Ordering::SeqCst);
        let running = self.running.clone();
        let services = self.services.clone();
        let event_tx = self.event_tx.clone();
        let hb_interval = self.config.heartbeat_interval_ms;

        tokio::spawn(async move {
            let mut ticker = interval(Duration::from_millis(hb_interval));
            while running.load(Ordering::SeqCst) {
                ticker.tick().await;
                for entry in services.iter() {
                    tracing::trace!(
                        service_id = %entry.service_id,
                        "heartbeat sent for service"
                    );
                    let _ = event_tx.send(RegistryEvent::Heartbeat(entry.service_id.clone()));
                }
            }
        });

        tracing::info!("service registry initialized");
        Ok(())
    }

    pub async fn register(&self, entry: ServiceEntry) -> Result<()> {
        tracing::info!(
            service_id = %entry.service_id,
            service_name = %entry.service_name,
            "registering service"
        );
        self.services.insert(entry.service_id.clone(), entry.clone());
        let _ = self.event_tx.send(RegistryEvent::Registered(entry));
        Ok(())
    }

    pub async fn deregister(&self, service_id: &str) -> Result<()> {
        tracing::info!(service_id = %service_id, "deregistering service");
        self.services.remove(service_id);
        let _ = self.event_tx.send(RegistryEvent::Deregistered(service_id.to_string()));
        Ok(())
    }

    pub async fn shutdown(&self) -> Result<()> {
        tracing::info!("shutting down service registry");
        self.running.store(false, Ordering::SeqCst);
        let count = self.services.len();
        self.services.clear();
        tracing::info!(services_deregistered = %count, "service registry shutdown complete");
        Ok(())
    }

    pub fn subscribe(&self) -> tokio::sync::broadcast::Receiver<RegistryEvent> {
        self.event_tx.subscribe()
    }
}
