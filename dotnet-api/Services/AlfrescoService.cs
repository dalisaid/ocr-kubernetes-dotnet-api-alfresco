using System.Text.Json;
using System.Text;
using OnboardingApi.Models;

namespace OnboardingApi.Services;

public class AlfrescoService
{
    private readonly HttpClient _http;
    private readonly IConfiguration _config;




    public AlfrescoService(HttpClient http, IConfiguration config)
    {



        _config = config;
        _http = http;


        string Username = config["Alfresco:Username"] ?? throw new InvalidOperationException("Username not configured");
        string Password = config["Alfresco:Password"] ?? throw new InvalidOperationException("Password not configured");
        string BaseUrl = config["Alfresco:BaseUrl"] ?? throw new InvalidOperationException("BaseUrl not configured");

        _http.BaseAddress = new Uri(BaseUrl);



        //basic auth
        var byteArray = System.Text.Encoding.ASCII.GetBytes($"{Username}:{Password}");
        _http.DefaultRequestHeaders.Authorization =
            new System.Net.Http.Headers.AuthenticationHeaderValue("Basic", Convert.ToBase64String(byteArray));


    }


    public async Task<string> CreateFolder(Client folderData) //creates folder inside of library with Cin
    {

        string parentNodeId = _config["Alfresco:FolderNodeId"] ?? throw new InvalidOperationException("FolderNodeId not configured");
        var payload = new
        {
            name = folderData.CIN,       // folder name in Alfresco
            nodeType = "cm:folder",
            properties = new Dictionary<string, object>
        {
            { "cm:title", $"{folderData.FirstName} {folderData.LastName}" },
            { "cm:description", $"Client {folderData.FirstName} {folderData.LastName}, Card Number: {folderData.BankCardNumber}" }
        }

        };

        var response = await _http.PostAsJsonAsync(
            $"alfresco/api/-default-/public/alfresco/versions/1/nodes/{parentNodeId}/children",
            payload);

        response.EnsureSuccessStatusCode();
        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        return json.GetProperty("entry").GetProperty("id").GetString()!;// return id of folder created to use in uploadfile
    }


    // uploads files into respective folder using cin 
    public async Task UploadFile(IFormFile file, string folderNodeId, string targetName)
    {
        using var content = new MultipartFormDataContent();
        var stream = file.OpenReadStream();
        content.Add(new StreamContent(stream), "filedata", targetName);

        var response = await _http.PostAsync(
            $"alfresco/api/-default-/public/alfresco/versions/1/nodes/{folderNodeId}/children",
            content);

        response.EnsureSuccessStatusCode();
    }

    /** For OCR project, we want to upload the file with the extracted text as metadata, so we need a separate method for that*/
    public async Task<string> OcrUploadFile(IFormFile file, string ocrText, string ocrEngine)
    {
        var folderNodeId = _config["Alfresco:OcrFolderNodeId"]
            ?? throw new InvalidOperationException("OcrFolderNodeId not configured");

        string nodeId;

        // =========================
        // 1. UPLOAD FILE ONLY
        // =========================
        using (var content = new MultipartFormDataContent())
        using (var stream = file.OpenReadStream())
        {
            var fileContent = new StreamContent(stream);
            fileContent.Headers.ContentType =
                new System.Net.Http.Headers.MediaTypeHeaderValue(file.ContentType);

            content.Add(fileContent, "filedata", file.FileName);
            content.Add(new StringContent(file.FileName), "name");
            content.Add(new StringContent("cm:content"), "nodeType");

            var response = await _http.PostAsync(
                $"alfresco/api/-default-/public/alfresco/versions/1/nodes/{folderNodeId}/children",
                content
            );

            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadFromJsonAsync<JsonElement>();
            nodeId = json.GetProperty("entry").GetProperty("id").GetString()!;
        }

        // =========================
        // 2. UPDATE METADATA
        // =========================
        //trying custom models -->
        //step 1: add aspect to node so we can add custom properties for ocr data

       /*  var aspectPayload = new
        {
            aspectNames = new[] { "ocr:ocrData" }
        };

        var aspectResponse = await _http.PutAsync(
            $"alfresco/api/-default-/public/alfresco/versions/1/nodes/{nodeId}",
            new StringContent(
                Newtonsoft.Json.JsonConvert.SerializeObject(aspectPayload),
                Encoding.UTF8,
                "application/json"
            )
        );
        Console.WriteLine(aspectResponse.StatusCode);
        Console.WriteLine(await aspectResponse.Content.ReadAsStringAsync());
        aspectResponse.EnsureSuccessStatusCode(); */
        //
        //step 2: update node with ocr metadata
        
        var metadataPayload = new
        {

            properties = new Dictionary<string, object>
            {   { "cm:name", file.FileName },
                { "cm:description", $"OCR Engine: {ocrEngine}\n\n---\n\nExtracted Text: {ocrText}" },
                
                
            },



        };

        var metaContent = new StringContent(
            Newtonsoft.Json.JsonConvert.SerializeObject(metadataPayload),
            Encoding.UTF8,
            "application/json"
        );

        var updateResponse = await _http.PutAsync(
            $"alfresco/api/-default-/public/alfresco/versions/1/nodes/{nodeId}",
            metaContent
        );

        updateResponse.EnsureSuccessStatusCode();

        return nodeId;
    }




}