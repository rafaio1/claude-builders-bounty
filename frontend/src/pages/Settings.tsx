import React from 'react';

const settingsSections = [
  {
    id: 'general',
    title: 'General Settings',
    fields: [
      { key: 'appName', label: 'Application Name', type: 'text', value: 'Tent of Trials' },
      { key: 'language', label: 'Language', type: 'select', value: 'en', options: ['en', 'es', 'fr', 'de', 'ja'] },
      { key: 'timezone', label: 'Timezone', type: 'select', value: 'UTC', options: ['UTC', 'EST', 'PST', 'CET'] },
    ],
  },
  {
    id: 'notifications',
    title: 'Notification Preferences',
    fields: [
      { key: 'emailNotif', label: 'Email Notifications', type: 'toggle', value: true },
      { key: 'desktopNotif', label: 'Desktop Notifications', type: 'toggle', value: false },
      { key: 'soundNotif', label: 'Sound Alerts', type: 'toggle', value: true },
      { key: 'digestFreq', label: 'Digest Frequency', type: 'select', value: 'daily', options: ['realtime', 'daily', 'weekly'] },
    ],
  },
  {
    id: 'security',
    title: 'Security',
    fields: [
      { key: 'twoFactor', label: 'Two-Factor Authentication', type: 'toggle', value: false },
      { key: 'sessionTimeout', label: 'Session Timeout (minutes)', type: 'number', value: 60 },
      { key: 'ipWhitelist', label: 'IP Whitelist', type: 'text', value: '' },
    ],
  },
  {
    id: 'features',
    title: 'Feature Flags',
    fields: [
      { key: 'betaFeatures', label: 'Beta Features', type: 'toggle', value: false },
      { key: 'experimental', label: 'Experimental Mode', type: 'toggle', value: false },
      { key: 'analytics', label: 'Analytics Collection', type: 'toggle', value: true },
    ],
  },
];

const Settings: React.FC = () => {
  const [activeSection, setActiveSection] = React.useState('general');
  const [dirty, setDirty] = React.useState(false);

  return (
    <div className="settings">
      <div className="settings-header">
        <h2>Settings</h2>
        {dirty && (
          <div className="settings-unsaved">
            <span>You have unsaved changes</span>
            <button className="btn-primary" onClick={() => setDirty(false)}>
              Save Changes
            </button>
          </div>
        )}
      </div>

      <div className="settings-body">
        <nav className="settings-nav">
          {settingsSections.map((section) => (
            <button
              key={section.id}
              className={`settings-nav-item ${activeSection === section.id ? 'active' : ''}`}
              onClick={() => setActiveSection(section.id)}
            >
              {section.title}
            </button>
          ))}
        </nav>

        <div className="settings-content">
          {settingsSections
            .filter((s) => s.id === activeSection)
            .map((section) => (
              <div key={section.id} className="settings-section">
                <h3>{section.title}</h3>
                <div className="settings-fields">
                  {(section.fields as any[]).map((field: any) => (
                    <div key={field.key} className="settings-field">
                      <label htmlFor={field.key}>{field.label}</label>
                      {field.type === 'toggle' ? (
                        <input
                          id={field.key}
                          type="checkbox"
                          defaultChecked={field.value}
                          onChange={() => setDirty(true)}
                        />
                      ) : field.type === 'select' ? (
                        <select
                          id={field.key}
                          defaultValue={field.value}
                          onChange={() => setDirty(true)}
                        >
                          {field.options.map((opt: string) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          id={field.key}
                          type={field.type}
                          defaultValue={field.value}
                          onChange={() => setDirty(true)}
                        />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
};

export default Settings;
