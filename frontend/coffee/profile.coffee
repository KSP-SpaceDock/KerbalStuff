# Background Uploading
window.upload_bg = (files, box) ->
    file = files[0]
    p = document.createElement('p')
    p.textContent = 'Uploading...'
    p.className = 'status'
    box.appendChild(p)
    box.querySelector('a').classList.add('hidden')
    progress = box.querySelector('.upload-progress')

    xhr = new XMLHttpRequest()
    xhr.open('POST', "/api/user/#{window.username}/update-bg")
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.upload.onprogress = (e) ->
        if e.lengthComputable
            progress.style.width = (e.loaded / e.total) * 100 + '%'
    xhr.onload = (e) ->
        if xhr.status != 200
            p.textContent = 'Please upload JPG or PNG only.'
            setTimeout(() ->
                box.removeChild(p)
                box.querySelector('a').classList.remove('hidden')
            , 3000)
        else
            resp = JSON.parse(xhr.responseText)
            p.textContent = 'Done!'
            document.getElementById('header-well').style.backgroundImage = 'url("' + resp.path + '")'
            setTimeout(() ->
                box.removeChild(p)
                box.querySelector('a').classList.remove('hidden')
            , 3000)
    formdata = new FormData()
    formdata.append('image', file)
    xhr.send(formdata)


# Handling of the change-password-dialog
$('#password-form').submit((e) ->
    e.preventDefault()

    # Disable the buttons until we get an response
    buttons = document.getElementsByClassName('btn-pw-change')
    for button in buttons
        button.setAttribute('disabled', '')

    old_password = $('#old-password').val()
    new_password = $('#new-password').val()
    new_password_confirm = $('#new-password-confirm').val()

    xhr = new XMLHttpRequest()
    xhr.open('POST', "/api/user/#{window.username}/change-password")
    xhr.setRequestHeader('Accept', 'application/json')
    # Triggered after we get an response from the server.
    # It's in the form {'error': bool, 'reason': string)
    xhr.onload = () ->
        result = JSON.parse(this.responseText)
        error_message_display = $('#error-message')

        if result.error == true
            error_message_display.html(result.reason)
            error_message_display.addClass('text-danger')
            error_message_display.removeClass('hidden')
            # Re-enable the buttons.
            for button in buttons
                button.removeAttribute('disabled')
        else
            error_message_display.html('Password changed successfully.')
            error_message_display.removeClass('text-danger')
            error_message_display.addClass('text-success')
            error_message_display.removeClass('hidden')
            # .modal('hide') doesn't work. Let's reload the page instead.
            # Delay it a bit to give the user a chance to read the response message.
            setTimeout((() -> window.location = window.location), 1000)

    form = new FormData()
    form.append('old-password', old_password)
    form.append('new-password', new_password)
    form.append('new-password-confirm', new_password_confirm)
    xhr.send(form)
)


resetPasswordModalDialog = () ->
    $('#password-form').trigger('reset')
    error_message_display = $('#error-message')
    error_message_display.html('')
    error_message_display.removeClass('text-danger')
    error_message_display.removeClass('text-success')
    error_message_display.addClass('hidden')

    buttons = document.getElementsByClassName('btn-pw-change')
    for button in buttons
        button.removeAttribute('disabled')

$('#change-password').on('hidden.bs.modal', resetPasswordModalDialog)
