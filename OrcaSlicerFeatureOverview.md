# A fast overview over the OrcaSlicer Backend and Frontend features

# Backend
## API Wrappers
Defaulted is the LocalAPI but with a toggle in the Settings Dashboard you can turn on the ExternalAPI, suitable for Docker container or other options.
The API Wrappers can be extended furthermore.

The idea behind multiple Wrappers is that all Wrappers have the same functionality and use the same functions. This is used so that the service can use a simple set of methods to have all functionality over different implementations.

### LocalAPI
This connects to a locally installed OrcaSlicer file, can be the Windows .exe, the .appimage, or any other format officially provided by [Orcaslicer](https://github.com/OrcaSlicer/OrcaSlicer).



**Methods:**
- **check_status**: checks the current status of the API:
    1. _unconfigured_: The provided path is empty, which means the API is not configured and the auto_path is not finding any file.
    2. _unavailable_: The provided path is nonexistent.
    3. _unhealthy_: The provided OrcaSlicer file is not working (due to a wrong file, etc).
    4. _healthy_: The provided OrcaSlicer file is working completely.
- **is_healthy**: checks if the current status is healthy.
- **_locate_orcaslicer**: find a OrcaSlicer in the systems PATH or in often used file locations of Windows and Linux systems. Only being called if check_status is called or the config is reloaded.
- **_sanitize_path**: clears any whitespaces off of the path. Prevents error because of wrong inputs. May be extended with other adjustments for sanitizing.


**Slicing Methods:**


### ExternalAPI
This can connect to a API running on a Server. Built to work with the [RestAPI made by AFKFelix](https://github.com/AFKFelix/orca-slicer-api) but can be easily adjusted. The API needs to fit into the requirements: It needs to work the same way as the LocalAPI works, or at least has to have the same features, otherwise the slicing would be inconsistent over different API solutions.

(Maybe also support a BambuStudio AppImage as it works with more Bambu specific files)

**Capabilities:**
- **health_check** _/health_ returns:
    ```json
    {
        status: "healthy" | "unhealthy";
        timestamp: string;
        checks: {
            orcaslicer: {
                available: boolean;
                version?: string;
                error?: string;
            };
            dataPath: {
                accessible: boolean;
                error?: string;
            };
        };
    }
    ```
- **list existing profiles** GET _/profiles/{category}_ returns a list of profiles.
- **add new profile** POST _/profiles/{category}_
- **get profile name** GET _/profiles/{category}/{name}_
- **slice a file** POST _/slice_

(further informations in the [swagger in the original API Repo](https://github.com/AFKFelix/orca-slicer-api/blob/main/swagger.json))


**Basic Methods:**
- **check_status**: checks the current status of the API:
    1. _unconfigured_: The provided URL is empty. --> The API is not set up.
    2. _unavailable_: The provided URL is not reachable, or a connection error occurs. Can be due to a not finished config or a incorrect entered URL/PORT.
    3. _unhealthy_: The provided URL is returning a unhealthy state: This would be a problem on the APIs Server side, not on the local side.
    4. _healthy_: The provided URL is returning a healthy state and should work flawlessly.
- **is_healthy**: checks if the current status is healthy.
- **_sanitize_url**: clears any whitespaces off of the URL provided by the config. Prevents error because of wrong inputs. May be extended with other adjustments for sanitizing.

**Slicing Methods:**
- **slice_file_async**: Runs asynchronous and slices the file, returns after the slice is finished or an error occured.

## Service
The Service uses the API Wrappers to slice files, the API Wrappers must work in the same way in order to make the Service work correctly.

- check_status: returns the current status, uses the corresponding API Wrapper method




# Frontend

Slicing can be started through the filemanager or the archive. The slice job is a popup where you can change some important settings for the slice and after that it starts the slicing job and shows through a toast message the current state of the slice. After the slice finishes it exports the gcode to the specified location.
